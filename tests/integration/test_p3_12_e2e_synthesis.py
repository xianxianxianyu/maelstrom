"""P3-12: E2E Synthesis Engine integration tests."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
import aiosqlite

from maelstrom.db.migrations import run_migrations
from maelstrom.db import synthesis_run_repo
from maelstrom.services import synthesis_service
from maelstrom.services.evidence_memory import SqliteEvidenceMemory, set_evidence_memory
from maelstrom.services.intent_classifier import classify_intent
from maelstrom.schemas.intent import IntentType, SessionContext
from maelstrom.schemas.llm_config import LLMProfile


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await run_migrations(conn)
    await conn.execute(
        "INSERT INTO sessions (id, title, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("s1", "Test", "active", "2025-01-01T00:00:00", "2025-01-01T00:00:00"),
    )
    await conn.commit()
    yield conn
    await conn.close()


@pytest.fixture
async def mem(db):
    m = SqliteEvidenceMemory(db)
    set_evidence_memory(m)
    return m


@pytest.fixture
def profile():
    return LLMProfile(provider="openai", model="gpt-4", api_key="test-key")


def _mock_llm():
    async def mock_call_llm(prompt, config, **kw):
        p = prompt.lower()
        if "search quer" in p:
            return '["query1", "query2"]'
        if "relevance" in p or "rate the" in p:
            return json.dumps([{"paper_id": "p1", "relevance": 0.9, "reason": "ok"}])
        if "extract" in p or "structured" in p:
            return json.dumps({"claims": [
                {"claim_type": "method_effectiveness", "text": "BERT works for NER",
                 "extracted_fields": {"problem": "NER", "method": "BERT"},
                 "confidence": 0.8, "source_span": "abstract"}
            ]})
        if "alignment" in p or "citation" in p:
            return json.dumps([{"claim_id": "c1", "aligned": True, "source_span": "s1", "alignment_score": 0.9}])
        if "conflict" in p or "consensus" in p:
            return json.dumps({
                "consensus": [{"statement": "BERT effective", "supporting_claim_ids": ["c1"], "strength": "strong"}],
                "conflicts": [], "open_questions": ["Low-resource?"],
            })
        if "feasibility" in p or "verdict" in p:
            return json.dumps({
                "gap_validity": "Valid", "existing_progress": "Partial",
                "resource_assessment": "Ok", "verdict": "advance",
                "reasoning": "Worth it", "confidence": 0.85,
            })
        if "summary" in p or "executive" in p:
            return "NER review summary."
        return "{}"
    return mock_call_llm


_LLM_PATCHES = [
    "maelstrom.graph.synthesis_nodes.targeted_retrieval.call_llm",
    "maelstrom.graph.synthesis_nodes.relevance_filtering.call_llm",
    "maelstrom.graph.synthesis_nodes.claim_extraction.call_llm",
    "maelstrom.graph.synthesis_nodes.citation_binding.call_llm",
    "maelstrom.graph.synthesis_nodes.conflict_analysis.call_llm",
    "maelstrom.graph.synthesis_nodes.feasibility_review.call_llm",
    "maelstrom.graph.synthesis_nodes.report_assembly.call_llm",
]


async def _run_synthesis(db, mem, profile, topic="NER", seed_paper=True):
    """Helper: run synthesis pipeline directly (no background task)."""
    if seed_paper:
        await mem.ingest_text("s1", "paper", "p1", "NER Transformer BERT", "BERT and Transformer achieve SOTA on NER tasks")

    get_db_mock = AsyncMock(return_value=db)
    patches = [patch(p, side_effect=_mock_llm()) for p in _LLM_PATCHES]
    patches.append(patch("maelstrom.db.database.get_db", get_db_mock))
    patches.append(patch("maelstrom.services.synthesis_service.get_db", get_db_mock))

    for p in patches:
        p.start()
    try:
        run = await synthesis_run_repo.create_synthesis_run(db, "s1", topic)
        run_id = run["id"]
        synthesis_service._run_state[run_id] = {"current_step": "pending", "result": None, "error": None}
        await synthesis_service._execute_run(run_id, "s1", topic, profile)
        return run_id
    finally:
        for p in patches:
            p.stop()


# --- E2E-01: Topic → Full Synthesis ---
@pytest.mark.asyncio
async def test_e2e_topic_full_synthesis(db, mem, profile):
    run_id = await _run_synthesis(db, mem, profile, "NER")
    run = await synthesis_run_repo.get_synthesis_run(db, run_id)
    assert run["status"] == "completed"
    result = json.loads(run["result_json"])
    assert "review_report" in result
    assert "feasibility_memo" in result


# --- E2E-03: SSE Event completeness ---
@pytest.mark.asyncio
async def test_e2e_sse_events(db, mem, profile):
    await mem.ingest_text("s1", "paper", "p1", "BERT for NER", "BERT achieves SOTA")
    get_db_mock = AsyncMock(return_value=db)
    patches = [patch(p, side_effect=_mock_llm()) for p in _LLM_PATCHES]
    patches.append(patch("maelstrom.db.database.get_db", get_db_mock))
    patches.append(patch("maelstrom.services.synthesis_service.get_db", get_db_mock))

    for p in patches:
        p.start()
    try:
        run = await synthesis_run_repo.create_synthesis_run(db, "s1", "NER")
        run_id = run["id"]
        synthesis_service._run_state[run_id] = {"current_step": "pending", "result": None, "error": None}
        q = synthesis_service.subscribe(run_id)
        await synthesis_service._execute_run(run_id, "s1", "NER", profile)
        events = []
        while not q.empty():
            events.append(q.get_nowait()["event"])
        synthesis_service.unsubscribe(run_id, q)
    finally:
        for p in patches:
            p.stop()

    step_starts = [e for e in events if e == "step_start"]
    step_completes = [e for e in events if e == "step_complete"]
    assert len(step_starts) == 7
    assert len(step_completes) == 7
    assert "claims_extracted" in events
    assert "result" in events
    assert "__done__" in events


# --- E2E-05: EvidenceMemory writeback ---
@pytest.mark.asyncio
async def test_e2e_evidence_memory_writeback(db, mem, profile):
    run_id = await _run_synthesis(db, mem, profile)
    hits = await mem.search("s1", "Review NER", limit=20)
    types = {h.source_type for h in hits}
    assert "review" in types or "claim" in types


# --- E2E-06: Router integration ---
@pytest.mark.asyncio
async def test_e2e_router_synthesis_intent():
    ctx = SessionContext(session_id="s1")
    intent = await classify_intent("帮我做文献综述", ctx)
    assert intent.intent == IntentType.synthesis


# --- E2E-07: Backward compatibility ---
@pytest.mark.asyncio
async def test_e2e_backward_compat_router():
    from maelstrom.main import app
    routes = [r.path for r in app.routes]
    assert any("/api/router" in r for r in routes)
    assert any("/api/gap" in r for r in routes)
    assert any("/api/chat" in r for r in routes)
    assert any("/api/synthesis" in r for r in routes)


# --- E2E-08: Retrieval failure ---
@pytest.mark.asyncio
async def test_e2e_retrieval_failure(db, mem, profile):
    try:
        run_id = await _run_synthesis(db, mem, profile, "Unknown Topic", seed_paper=False)
    except Exception:
        pass
    # Check the run is marked failed
    runs = await synthesis_run_repo.list_by_session(db, "s1")
    failed_runs = [r for r in runs if r["status"] == "failed"]
    assert len(failed_runs) >= 1
