"""P3-01: Synthesis Graph + Service tests."""
from __future__ import annotations

import asyncio
import json

import pytest

from unittest.mock import AsyncMock, patch

from maelstrom.graph.synthesis_builder import SynthesisEngineGraph, NODE_ORDER
from maelstrom.db.migrations import run_migrations
from maelstrom.db import synthesis_run_repo


# --- Graph tests ---

def test_graph_node_count():
    assert len(NODE_ORDER) == 7
    assert len(SynthesisEngineGraph.NODES) == 7


@pytest.mark.asyncio
async def test_graph_passthrough():
    """Nodes run without error when targeted_papers exist."""
    mem = AsyncMock()
    mem.search.return_value = [AsyncMock(source_type="paper", source_id="p1", title="P", snippet="abs")]
    mem.ingest_text = AsyncMock()
    graph = SynthesisEngineGraph()
    state = {"topic": "NER", "session_id": "s1", "llm_config": {}, "filtered_papers": [{"paper_id": "p1", "title": "P", "abstract": "abs"}]}
    with patch("maelstrom.graph.synthesis_nodes.targeted_retrieval.get_evidence_memory", return_value=mem):
        with patch("maelstrom.graph.synthesis_nodes.targeted_retrieval.call_llm", return_value='["q1"]'):
            with patch("maelstrom.graph.synthesis_nodes.relevance_filtering.call_llm", return_value='[{"paper_id":"p1","relevance":0.9,"reason":"ok"}]'):
                with patch("maelstrom.graph.synthesis_nodes.claim_extraction.call_llm", return_value='{"claims":[]}'):
                    with patch("maelstrom.graph.synthesis_nodes.citation_binding.call_llm", return_value='[]'):
                        with patch("maelstrom.graph.synthesis_nodes.conflict_analysis.call_llm", return_value='{"consensus":[],"conflicts":[],"open_questions":[]}'):
                            with patch("maelstrom.graph.synthesis_nodes.feasibility_review.call_llm", return_value='{"gap_validity":"ok","existing_progress":"ok","resource_assessment":"ok","verdict":"advance","reasoning":"ok","confidence":0.8}'):
                                with patch("maelstrom.graph.synthesis_nodes.report_assembly.call_llm", return_value="Summary"):
                                    with patch("maelstrom.graph.synthesis_nodes.report_assembly.get_evidence_memory", return_value=mem):
                                        result = await graph.run(state)
    assert result.get("error") is None
    assert result["current_step"] == "report_assembly"


@pytest.mark.asyncio
async def test_route_no_papers():
    """targeted_retrieval with no papers → error."""
    mem = AsyncMock()
    mem.search.return_value = []
    graph = SynthesisEngineGraph()
    state = {"topic": "NER", "session_id": "s1", "llm_config": {}}
    with patch("maelstrom.graph.synthesis_nodes.targeted_retrieval.get_evidence_memory", return_value=mem):
        with patch("maelstrom.graph.synthesis_nodes.targeted_retrieval.call_llm", return_value='["q1"]'):
            result = await graph.run(state)
    assert result["error"] == "No papers found for synthesis"


# --- DB repo tests ---

@pytest.fixture
async def db():
    import aiosqlite
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await run_migrations(conn)
    # Create a session for FK
    await conn.execute(
        "INSERT INTO sessions (id, title, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("s1", "Test", "active", "2025-01-01T00:00:00", "2025-01-01T00:00:00"),
    )
    await conn.commit()
    yield conn
    await conn.close()


@pytest.mark.asyncio
async def test_db_table_created(db):
    cur = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='synthesis_runs'")
    row = await cur.fetchone()
    assert row is not None


@pytest.mark.asyncio
async def test_synthesis_run_repo_crud(db):
    run = await synthesis_run_repo.create_synthesis_run(db, "s1", "NER")
    assert run["status"] == "pending"
    run_id = run["id"]

    fetched = await synthesis_run_repo.get_synthesis_run(db, run_id)
    assert fetched is not None
    assert fetched["topic"] == "NER"

    await synthesis_run_repo.update_synthesis_run_status(db, run_id, "running")
    fetched = await synthesis_run_repo.get_synthesis_run(db, run_id)
    assert fetched["status"] == "running"

    await synthesis_run_repo.update_synthesis_run_result(db, run_id, '{"test": true}')
    fetched = await synthesis_run_repo.get_synthesis_run(db, run_id)
    assert json.loads(fetched["result_json"]) == {"test": True}

    await synthesis_run_repo.update_synthesis_run_status(db, run_id, "completed")
    fetched = await synthesis_run_repo.get_synthesis_run(db, run_id)
    assert fetched["status"] == "completed"
    assert fetched["completed_at"] is not None

    runs = await synthesis_run_repo.list_by_session(db, "s1")
    assert len(runs) == 1

    count = await synthesis_run_repo.count_by_session(db, "s1")
    assert count == 1
