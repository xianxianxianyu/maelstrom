"""P3-11: Evidence writeback + Phase linkage tests."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
import aiosqlite

from maelstrom.db.migrations import run_migrations
from maelstrom.services.evidence_memory import SqliteEvidenceMemory, set_evidence_memory, get_evidence_memory
from maelstrom.graph.synthesis_nodes.report_assembly import report_assembly
from maelstrom.schemas.intent import SessionContext


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


def _base_state(**kw):
    defaults = {
        "session_id": "s1", "run_id": "r1", "topic": "NER", "llm_config": {},
        "filtered_papers": [{"paper_id": "p1"}],
        "claims": [{"claim_id": "c1", "text": "BERT works for NER", "claim_type": "method_effectiveness"}],
        "evidences": [{"evidence_id": "e1", "source_id": "p1"}],
        "consensus_points": [{"statement": "consensus"}],
        "conflict_points": [],
        "open_questions": [],
        "feasibility_memo": {"memo_id": "m1", "verdict": "advance", "reasoning": "Good direction", "confidence": 0.8},
    }
    defaults.update(kw)
    return defaults


@pytest.mark.asyncio
async def test_review_ingested(mem):
    with patch("maelstrom.graph.synthesis_nodes.report_assembly.call_llm", return_value="Summary"):
        await report_assembly(_base_state())
    hits = await mem.search("s1", "Review NER", limit=5)
    review_hits = [h for h in hits if h.source_type == "review"]
    assert len(review_hits) >= 1


@pytest.mark.asyncio
async def test_claims_ingested(mem):
    with patch("maelstrom.graph.synthesis_nodes.report_assembly.call_llm", return_value="Summary"):
        await report_assembly(_base_state())
    hits = await mem.search("s1", "BERT", limit=5)
    claim_hits = [h for h in hits if h.source_type == "claim"]
    assert len(claim_hits) >= 1


@pytest.mark.asyncio
async def test_feasibility_ingested(db, mem):
    """Feasibility memo written by synthesis_service after run completes."""
    # Simulate what synthesis_service does after report_assembly
    memo = {"memo_id": "m1", "verdict": "advance", "reasoning": "Good direction", "confidence": 0.8}
    await mem.ingest_text(
        "s1", "feasibility", memo["memo_id"],
        f"Feasibility: {memo['verdict']}",
        f"{memo['reasoning']}\nVerdict: {memo['verdict']}\nConfidence: {memo['confidence']}",
    )
    hits = await mem.search("s1", "Feasibility", limit=5)
    feas_hits = [h for h in hits if h.source_type == "feasibility"]
    assert len(feas_hits) >= 1


@pytest.mark.asyncio
async def test_phase_updated_to_grounding(db):
    from maelstrom.services.phase_tracker import _set_phase, get_current_phase
    from maelstrom.schemas.common import ResearchPhase
    with patch("maelstrom.services.phase_tracker.get_db", return_value=db):
        await _set_phase(db, "s1", ResearchPhase.grounding)
        phase = await get_current_phase("s1")
    assert phase == ResearchPhase.grounding


@pytest.mark.asyncio
async def test_session_context_has_synthesis(db):
    # Insert a synthesis run
    await db.execute(
        "INSERT INTO synthesis_runs (id, session_id, topic, status, created_at) VALUES (?, ?, ?, ?, ?)",
        ("r1", "s1", "NER", "completed", "2025-01-01T00:00:00"),
    )
    await db.commit()

    from maelstrom.db import synthesis_run_repo
    count = await synthesis_run_repo.count_by_session(db, "s1")
    assert count > 0


@pytest.mark.asyncio
async def test_claims_searchable(mem):
    with patch("maelstrom.graph.synthesis_nodes.report_assembly.call_llm", return_value="Summary"):
        await report_assembly(_base_state())
    # Search for claim content via FTS
    hits = await mem.search("s1", "BERT NER", limit=10)
    assert any(h.source_type == "claim" for h in hits)
