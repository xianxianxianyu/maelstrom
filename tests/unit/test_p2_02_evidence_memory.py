"""P2-02: EvidenceMemory SQLite FTS tests."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite
import pytest

from maelstrom.db.migrations import run_migrations
from maelstrom.schemas.gap import GapItem, GapScores
from maelstrom.schemas.paper import Author, ExternalIds, PaperRecord
from maelstrom.services.evidence_memory import (
    EvidenceHit,
    SessionMemorySummary,
    SqliteEvidenceMemory,
)


@pytest.fixture
async def mem():
    """Create an in-memory SQLite DB with migrations and return SqliteEvidenceMemory."""
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys=ON")
    await run_migrations(db)
    # Create a test session
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO sessions (id, title, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("s1", "Test Session", "active", now, now),
    )
    await db.execute(
        "INSERT INTO sessions (id, title, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("s2", "Other Session", "active", now, now),
    )
    await db.commit()
    memory = SqliteEvidenceMemory(db=db)
    yield memory
    await db.close()


def _make_paper(paper_id: str = "p1", title: str = "Attention Is All You Need") -> PaperRecord:
    return PaperRecord(
        paper_id=paper_id,
        title=title,
        authors=[Author(name="Vaswani"), Author(name="Shazeer")],
        abstract="We propose a new architecture based on attention mechanisms.",
        year=2017,
        source="arxiv",
        external_ids=ExternalIds(),
        retrieved_at=datetime.now(timezone.utc),
    )


def _make_gap(gap_id: str = "gap-1", title: str = "Cross-lingual Transfer Gap") -> GapItem:
    return GapItem(
        gap_id=gap_id,
        title=title,
        summary="Limited work on cross-lingual transfer for low-resource languages.",
        gap_type=["method", "dataset"],
        confidence=0.8,
        scores=GapScores(novelty=0.7, feasibility=0.8, impact=0.9),
        session_id="s1",
        created_at=datetime.now(timezone.utc),
    )


# ── Table creation ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evidence_memory_table_created(mem: SqliteEvidenceMemory):
    db = await mem._get_db()
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='evidence_memory'"
    )
    row = await cursor.fetchone()
    assert row is not None


@pytest.mark.asyncio
async def test_fts_table_created(mem: SqliteEvidenceMemory):
    db = await mem._get_db()
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='evidence_memory_fts'"
    )
    row = await cursor.fetchone()
    assert row is not None


# ── Ingest tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_paper(mem: SqliteEvidenceMemory):
    paper = _make_paper()
    eid = await mem.ingest_paper("s1", paper)
    assert eid  # non-empty UUID

    # Should be searchable by title
    hits = await mem.search("s1", "Attention")
    assert len(hits) >= 1
    assert any("Attention" in h.title for h in hits)


@pytest.mark.asyncio
async def test_ingest_gap(mem: SqliteEvidenceMemory):
    gap = _make_gap()
    eid = await mem.ingest_gap("s1", gap)
    assert eid

    hits = await mem.search("s1", "cross-lingual")
    assert len(hits) >= 1


@pytest.mark.asyncio
async def test_ingest_text(mem: SqliteEvidenceMemory):
    eid = await mem.ingest_text("s1", "chat", "msg-1", "User question", "How does BERT work?")
    assert eid

    hits = await mem.search("s1", "BERT")
    assert len(hits) >= 1
    assert hits[0].source_type == "chat"


# ── Search tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_bm25_ranking(mem: SqliteEvidenceMemory):
    """Multiple entries — search should return results ranked by relevance."""
    await mem.ingest_text("s1", "paper", "p1", "Transformer Architecture", "Self-attention mechanism for NLP")
    await mem.ingest_text("s1", "paper", "p2", "CNN for Images", "Convolutional neural networks for image classification")
    await mem.ingest_text("s1", "paper", "p3", "Attention in NLP", "Attention mechanisms are key to modern NLP transformers")

    hits = await mem.search("s1", "attention NLP")
    assert len(hits) >= 1
    # Results should be returned (BM25 ordering)
    titles = [h.title for h in hits]
    assert any("Attention" in t or "Transformer" in t for t in titles)


@pytest.mark.asyncio
async def test_search_session_isolation(mem: SqliteEvidenceMemory):
    """Session A's records should not appear in session B's search."""
    await mem.ingest_text("s1", "paper", "p1", "Paper A", "Unique content alpha")
    await mem.ingest_text("s2", "paper", "p2", "Paper B", "Unique content beta")

    hits_s1 = await mem.search("s1", "alpha")
    hits_s2 = await mem.search("s2", "alpha")

    assert len(hits_s1) >= 1
    assert len(hits_s2) == 0


@pytest.mark.asyncio
async def test_search_highlight_snippet(mem: SqliteEvidenceMemory):
    await mem.ingest_text("s1", "paper", "p1", "Test Paper", "The transformer model uses self-attention")

    hits = await mem.search("s1", "transformer")
    assert len(hits) >= 1
    assert "<b>" in hits[0].snippet


@pytest.mark.asyncio
async def test_search_no_results(mem: SqliteEvidenceMemory):
    hits = await mem.search("s1", "nonexistent_xyz_query")
    assert hits == []


@pytest.mark.asyncio
async def test_search_empty_query(mem: SqliteEvidenceMemory):
    hits = await mem.search("s1", "")
    assert hits == []


# ── Summary tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_session_summary(mem: SqliteEvidenceMemory):
    await mem.ingest_paper("s1", _make_paper("p1"))
    await mem.ingest_paper("s1", _make_paper("p2"))
    await mem.ingest_paper("s1", _make_paper("p3"))
    await mem.ingest_gap("s1", _make_gap("g1"))
    await mem.ingest_gap("s1", _make_gap("g2"))

    summary = await mem.get_session_summary("s1")
    assert summary.paper_count == 3
    assert summary.gap_count == 2
    assert summary.total_entries == 5


@pytest.mark.asyncio
async def test_get_session_summary_empty(mem: SqliteEvidenceMemory):
    summary = await mem.get_session_summary("s1")
    assert summary.paper_count == 0
    assert summary.total_entries == 0
