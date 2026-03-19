"""P1-15: End-to-end integration tests for the full Gap Engine flow."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from maelstrom.db import database
from maelstrom.db.migrations import run_migrations
from maelstrom.services import gap_service, llm_config_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
async def use_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.set_db_path(tmp.name)
    db = await database.get_db()
    await run_migrations(db)
    gap_service._run_state.clear()
    from maelstrom.services.event_bus import EventBus, set_event_bus
    set_event_bus(EventBus())
    from maelstrom.schemas.llm_config import MaelstromConfig
    llm_config_service._config = MaelstromConfig()
    yield
    await database.close_db()
    os.unlink(tmp.name)


@pytest.fixture
async def client():
    from maelstrom.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def session_id(client):
    resp = await client.post("/api/sessions", json={"title": "E2ETest"})
    return resp.json()["id"]


@pytest.fixture
async def configured_client(client):
    from maelstrom.schemas.llm_config import LLMProfile, MaelstromConfig
    llm_config_service._config = MaelstromConfig(
        profiles={"default": LLMProfile(name="Default", model="gpt-4o", api_key="sk-test")},
        active_profile="default",
    )
    return client


# ---------------------------------------------------------------------------
# Helpers — mock LLM responses for each node
# ---------------------------------------------------------------------------

_QE_RESPONSE = json.dumps(["transformer efficiency methods", "attention mechanism optimization"])

_CM_RESPONSE = json.dumps([
    {"paper_id": "arxiv_1", "tasks": ["NER"], "methods": ["CRF"], "datasets": ["CoNLL"], "metrics": ["F1"]},
    {"paper_id": "s2_1", "tasks": ["NER"], "methods": ["BiLSTM"], "datasets": ["OntoNotes"], "metrics": ["F1"]},
])

_GH_RESPONSE = json.dumps([
    {
        "title": "Missing Medical NER",
        "summary": "No evaluation on medical domain NER",
        "gap_type": "dataset",
        "evidence_refs": ["arxiv_1"],
        "confidence": 0.85,
    },
    {
        "title": "Transformer for NER",
        "summary": "Transformer models underexplored for NER",
        "gap_type": "method",
        "evidence_refs": ["s2_1"],
        "confidence": 0.75,
    },
])

_GC_RESPONSE = json.dumps([
    {"title": "Missing Medical NER", "verdict": "keep", "revised_summary": None},
    {"title": "Transformer for NER", "verdict": "keep", "revised_summary": None},
])

_RP_RESPONSE = json.dumps([
    {"title": "Missing Medical NER", "novelty": 0.9, "feasibility": 0.7, "impact": 0.8},
    {"title": "Transformer for NER", "novelty": 0.6, "feasibility": 0.8, "impact": 0.7},
])


def _make_llm_side_effect():
    """Return a side_effect function that returns different responses per node module."""
    call_count = {"qe": 0, "cm": 0, "gh": 0, "gc": 0, "rp": 0}

    async def _fake_llm(prompt, llm_config, **kwargs):
        # Detect which node is calling based on prompt content
        if "search queries" in prompt.lower():
            return _QE_RESPONSE
        elif "extract structured information" in prompt.lower() or "tasks" in prompt and "methods" in prompt and "datasets" in prompt:
            return _CM_RESPONSE
        elif "research gap hypotheses" in prompt.lower() or "gap_type" in prompt:
            return _GH_RESPONSE
        elif "critic" in prompt.lower() or "verdict" in prompt.lower():
            return _GC_RESPONSE
        elif "novelty" in prompt.lower() and "feasibility" in prompt.lower() and "impact" in prompt.lower():
            return _RP_RESPONSE
        return "[]"

    return _fake_llm


def _mock_adapter_search():
    """Create a mock PaperRetriever that returns fake papers."""
    from maelstrom.services.paper_retriever import SearchResult, SourceStatus

    fake_papers = [
        MagicMock(
            model_dump=lambda **kw: {
                "paper_id": "arxiv_1", "title": "Attention for NER",
                "authors": [{"name": "Alice"}], "year": 2024, "venue": "ACL",
                "source": "arxiv", "doi": "10.1234/a1",
            }
        ),
        MagicMock(
            model_dump=lambda **kw: {
                "paper_id": "s2_1", "title": "BiLSTM NER Study",
                "authors": [{"name": "Bob"}], "year": 2023, "venue": "EMNLP",
                "source": "s2", "doi": "10.1234/s1",
            }
        ),
    ]
    fake_statuses = [
        SourceStatus(source="arxiv", status="ok", count=1, error=None),
        SourceStatus(source="s2", status="ok", count=1, error=None),
    ]
    result = SearchResult(papers=fake_papers, source_statuses=fake_statuses)

    mock_retriever = AsyncMock()
    mock_retriever.search_with_fallback = AsyncMock(return_value=result)
    return mock_retriever


def _all_llm_patches():
    """Patch all call_llm functions across nodes."""
    fake = _make_llm_side_effect()
    return [
        patch("maelstrom.graph.nodes.query_expansion.call_llm", side_effect=fake),
        patch("maelstrom.graph.nodes.coverage_matrix.call_llm", side_effect=fake),
        patch("maelstrom.graph.nodes.gap_hypothesis.call_llm", side_effect=fake),
        patch("maelstrom.graph.nodes.gap_critic.call_llm", side_effect=fake),
        patch("maelstrom.graph.nodes.ranking_packaging.call_llm", side_effect=fake),
    ]


async def _wait_run(run_id: str, timeout: float = 10.0):
    for _ in range(int(timeout / 0.1)):
        status = await gap_service.get_status(run_id)
        if status and status["status"] in ("completed", "failed"):
            return status
        await asyncio.sleep(0.1)
    return await gap_service.get_status(run_id)


def _start_run_with_mocks():
    """Context manager stack: patch all LLM calls + adapter search methods."""
    from contextlib import ExitStack
    from maelstrom.services.paper_retriever import SearchResult, SourceStatus

    fake_papers = [
        MagicMock(model_dump=lambda **kw: {
            "paper_id": "arxiv_1", "title": "Attention for NER",
            "authors": [{"name": "Alice"}], "year": 2024, "venue": "ACL",
            "source": "arxiv", "doi": "10.1234/a1",
        }),
        MagicMock(model_dump=lambda **kw: {
            "paper_id": "s2_1", "title": "BiLSTM NER Study",
            "authors": [{"name": "Bob"}], "year": 2023, "venue": "EMNLP",
            "source": "s2", "doi": "10.1234/s1",
        }),
    ]
    fake_statuses = [
        SourceStatus(source="arxiv", status="ok", count=1, error=None),
        SourceStatus(source="s2", status="ok", count=1, error=None),
    ]
    fake_result = SearchResult(papers=fake_papers, source_statuses=fake_statuses)

    mock_retriever = AsyncMock()
    mock_retriever.search_with_fallback = AsyncMock(return_value=fake_result)

    patches = _all_llm_patches() + [
        patch("maelstrom.services.paper_retriever.PaperRetriever", return_value=mock_retriever),
    ]
    stack = ExitStack()
    for p in patches:
        stack.enter_context(p)
    return stack


# ---------------------------------------------------------------------------
# Test 1: Full Gap Engine flow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_gap_engine_full(configured_client, session_id):
    """Complete flow: topic → ranked_gaps + topic_candidates."""
    with _start_run_with_mocks():
        resp = await configured_client.post("/api/gap/run", json={
            "topic": "NER efficiency", "session_id": session_id,
        })
        assert resp.status_code == 202
        run_id = resp.json()["run_id"]
        status = await _wait_run(run_id)

    assert status["status"] == "completed"

    # Verify result structure
    resp = await configured_client.get(f"/api/gap/run/{run_id}/result")
    assert resp.status_code == 200
    result = resp.json()
    assert "ranked_gaps" in result
    assert "topic_candidates" in result
    assert "papers" in result
    assert "coverage_matrix" in result
    assert len(result["papers"]) >= 1
    assert len(result["ranked_gaps"]) >= 1
    # Each gap should have scores
    for gap in result["ranked_gaps"]:
        assert "title" in gap
        assert "scores" in gap or "weighted_score" in gap


# ---------------------------------------------------------------------------
# Test 2: Degraded search — one source fails
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_search_degraded(configured_client, session_id):
    """One source times out, others still return results."""
    from maelstrom.services.paper_retriever import SearchResult, SourceStatus

    fake_papers = [MagicMock(model_dump=lambda **kw: {
        "paper_id": "arxiv_1", "title": "Paper A", "authors": [],
        "year": 2024, "venue": "ACL", "source": "arxiv", "doi": "10.1/a",
    })]
    degraded_result = SearchResult(
        papers=fake_papers,
        source_statuses=[
            SourceStatus(source="arxiv", status="ok", count=1, error=None),
            SourceStatus(source="s2", status="timeout", count=0, error="Timed out"),
        ],
    )
    mock_retriever = AsyncMock()
    mock_retriever.search_with_fallback = AsyncMock(return_value=degraded_result)

    patches = _all_llm_patches() + [
        patch("maelstrom.services.paper_retriever.PaperRetriever", return_value=mock_retriever),
    ]
    from contextlib import ExitStack
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        resp = await configured_client.post("/api/gap/run", json={
            "topic": "NER methods", "session_id": session_id,
        })
        run_id = resp.json()["run_id"]
        status = await _wait_run(run_id)

    assert status["status"] == "completed"
    result_resp = await configured_client.get(f"/api/gap/run/{run_id}/result")
    result = result_resp.json()
    # Should still have papers from the working source
    assert len(result["papers"]) >= 1
    # search_result should show source statuses
    statuses = result["search_result"]["source_statuses"]
    status_map = {s["source"]: s["status"] for s in statuses}
    assert status_map.get("arxiv") == "ok"
    assert status_map.get("s2") == "timeout"


# ---------------------------------------------------------------------------
# Test 3: All sources fail → run fails
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_search_all_fail(configured_client, session_id):
    """All sources fail → run should fail with error."""
    from maelstrom.services.paper_retriever import SearchResult, SourceStatus

    fail_result = SearchResult(
        papers=[],
        source_statuses=[
            SourceStatus(source="arxiv", status="error", count=0, error="Connection refused"),
            SourceStatus(source="s2", status="error", count=0, error="Connection refused"),
        ],
    )
    mock_retriever = AsyncMock()
    mock_retriever.search_with_fallback = AsyncMock(return_value=fail_result)

    patches = _all_llm_patches() + [
        patch("maelstrom.services.paper_retriever.PaperRetriever", return_value=mock_retriever),
    ]
    from contextlib import ExitStack
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        resp = await configured_client.post("/api/gap/run", json={
            "topic": "NER methods", "session_id": session_id,
        })
        run_id = resp.json()["run_id"]
        status = await _wait_run(run_id)

    assert status["status"] == "failed"


# ---------------------------------------------------------------------------
# Test 4: SSE complete flow — all step events received
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_sse_complete_flow(configured_client, session_id):
    """SSE stream delivers step_start/step_complete for all 8 nodes + result."""
    with _start_run_with_mocks():
        # Subscribe BEFORE starting the run to avoid race
        resp = await configured_client.post("/api/gap/run", json={
            "topic": "NER efficiency", "session_id": session_id,
        })
        run_id = resp.json()["run_id"]

        q = gap_service.subscribe(run_id)
        events = []
        try:
            status = await _wait_run(run_id)
            # Drain all events from queue
            while not q.empty():
                events.append(await q.get())
        finally:
            gap_service.unsubscribe(run_id, q)

    assert status["status"] == "completed"

    event_types = [e["event"] for e in events]
    # Should have step_start and step_complete for each of 8 nodes
    step_starts = [e for e in events if e["event"] == "step_start"]
    step_completes = [e for e in events if e["event"] == "step_complete"]
    assert len(step_starts) == 8
    assert len(step_completes) == 8

    # Verify ordering: each step_start before its step_complete
    expected_steps = [
        "topic_intake", "query_expansion", "paper_retrieval", "normalize_dedup",
        "coverage_matrix", "gap_hypothesis", "gap_critic", "ranking_packaging",
    ]
    start_names = [json.loads(e["data"])["step"] for e in step_starts]
    complete_names = [json.loads(e["data"])["step"] for e in step_completes]
    assert start_names == expected_steps
    assert complete_names == expected_steps

    # Should have papers_found, matrix_ready, and result events
    assert "papers_found" in event_types
    assert "matrix_ready" in event_types
    assert "result" in event_types


# ---------------------------------------------------------------------------
# Test 5: Gap → QA share
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_gap_to_qa_share(configured_client, session_id):
    """After gap run completes, share-to-qa endpoint works."""
    with _start_run_with_mocks():
        resp = await configured_client.post("/api/gap/run", json={
            "topic": "NER efficiency", "session_id": session_id,
        })
        run_id = resp.json()["run_id"]
        await _wait_run(run_id)

    mock_share = AsyncMock(return_value={"shared": 2, "failed": 0, "skipped": 0})
    with patch("maelstrom.api.gap.share_papers_to_qa", mock_share):
        resp = await configured_client.post(
            f"/api/gap/run/{run_id}/share-to-qa",
            json={"session_id": session_id},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["shared"] == 2
    mock_share.assert_called_once()


# ---------------------------------------------------------------------------
# Test 6: Result persisted in DB
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_result_persisted(configured_client, session_id):
    """gap_runs and run_papers tables have correct data after completion."""
    with _start_run_with_mocks():
        resp = await configured_client.post("/api/gap/run", json={
            "topic": "NER efficiency", "session_id": session_id,
        })
        run_id = resp.json()["run_id"]
        await _wait_run(run_id)

    from maelstrom.db import gap_run_repo, run_paper_repo
    db = await database.get_db()

    # gap_runs row
    run = await gap_run_repo.get_gap_run(db, run_id)
    assert run is not None
    assert run["status"] == "completed"
    assert run["topic"] == "NER efficiency"
    assert run["completed_at"] is not None
    result = json.loads(run["result_json"])
    assert "ranked_gaps" in result
    assert "papers" in result

    # run_papers rows
    papers = await run_paper_repo.list_by_run(db, run_id)
    assert len(papers) >= 1
    paper_data = json.loads(papers[0]["paper_json"])
    assert "paper_id" in paper_data
    assert "title" in paper_data


# ---------------------------------------------------------------------------
# Test 7: Concurrent runs don't interfere
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_concurrent_runs(configured_client, session_id):
    """Two runs on the same session complete independently."""
    with _start_run_with_mocks():
        resp1 = await configured_client.post("/api/gap/run", json={
            "topic": "NER methods", "session_id": session_id,
        })
        resp2 = await configured_client.post("/api/gap/run", json={
            "topic": "Transformer optimization", "session_id": session_id,
        })
        run_id_1 = resp1.json()["run_id"]
        run_id_2 = resp2.json()["run_id"]

        status1 = await _wait_run(run_id_1)
        status2 = await _wait_run(run_id_2)

    assert status1["status"] == "completed"
    assert status2["status"] == "completed"
    assert run_id_1 != run_id_2

    # Both have results
    r1 = await configured_client.get(f"/api/gap/run/{run_id_1}/result")
    r2 = await configured_client.get(f"/api/gap/run/{run_id_2}/result")
    assert r1.status_code == 200
    assert r2.status_code == 200


# ---------------------------------------------------------------------------
# Test 8: Papers endpoint returns correct data
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_papers_endpoint(configured_client, session_id):
    """GET /papers returns persisted papers after run completes."""
    with _start_run_with_mocks():
        resp = await configured_client.post("/api/gap/run", json={
            "topic": "NER efficiency", "session_id": session_id,
        })
        run_id = resp.json()["run_id"]
        await _wait_run(run_id)

    resp = await configured_client.get(f"/api/gap/run/{run_id}/papers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["papers"]) >= 1
    assert "paper_id" in data["papers"][0]


# ---------------------------------------------------------------------------
# Test 9: Matrix endpoint returns correct data
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_matrix_endpoint(configured_client, session_id):
    """GET /matrix returns coverage matrix after run completes."""
    with _start_run_with_mocks():
        resp = await configured_client.post("/api/gap/run", json={
            "topic": "NER efficiency", "session_id": session_id,
        })
        run_id = resp.json()["run_id"]
        await _wait_run(run_id)

    resp = await configured_client.get(f"/api/gap/run/{run_id}/matrix")
    assert resp.status_code == 200
    data = resp.json()
    assert "cells" in data
    assert "summary" in data
