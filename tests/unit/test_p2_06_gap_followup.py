"""P2-06: Gap followup enrichment tests."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import aiosqlite
import pytest

from maelstrom.db.migrations import run_migrations
from maelstrom.schemas.paper import Author, ExternalIds, PaperRecord
from maelstrom.services.evidence_memory import EvidenceHit, SqliteEvidenceMemory
from maelstrom.services.gap_followup_service import enrich_gap_followup


@pytest.fixture
async def mem():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys=ON")
    await run_migrations(db)
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO sessions (id, title, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("s1", "Test", "active", now, now),
    )
    await db.commit()
    memory = SqliteEvidenceMemory(db=db)
    yield memory
    await db.close()


@pytest.mark.asyncio
async def test_enrich_with_gap_ref(mem):
    await mem.ingest_text("s1", "gap", "gap-1", "Cross-lingual Gap", "Limited cross-lingual transfer work")
    await mem.ingest_text("s1", "paper", "p1", "BERT Paper", "BERT for multilingual NLP")

    with patch("maelstrom.services.gap_followup_service.get_evidence_memory", return_value=mem):
        result = await enrich_gap_followup("s1", "展开说说这个 gap", gap_ref="gap-1")
        assert "基于以下已有研究上下文" in result
        assert "展开说说这个 gap" in result


@pytest.mark.asyncio
async def test_enrich_without_gap_ref(mem):
    await mem.ingest_text("s1", "paper", "p1", "Attention Paper", "Self-attention mechanism for NLP")

    with patch("maelstrom.services.gap_followup_service.get_evidence_memory", return_value=mem):
        result = await enrich_gap_followup("s1", "attention mechanism")
        assert "基于以下已有研究上下文" in result


@pytest.mark.asyncio
async def test_enrich_no_hits(mem):
    with patch("maelstrom.services.gap_followup_service.get_evidence_memory", return_value=mem):
        result = await enrich_gap_followup("s1", "完全无关的问题 xyz")
        assert result == "完全无关的问题 xyz"


@pytest.mark.asyncio
async def test_enriched_format(mem):
    await mem.ingest_text("s1", "gap", "gap-1", "Test Gap", "Some gap content here")

    with patch("maelstrom.services.gap_followup_service.get_evidence_memory", return_value=mem):
        result = await enrich_gap_followup("s1", "详细说说", gap_ref="gap-1")
        assert result.startswith("基于以下已有研究上下文")
        assert "用户问题：详细说说" in result


@pytest.mark.asyncio
async def test_enrich_search_error():
    """Search error should return original input."""
    mock_mem = MagicMock()
    mock_mem.search = AsyncMock(side_effect=RuntimeError("db error"))

    with patch("maelstrom.services.gap_followup_service.get_evidence_memory", return_value=mock_mem):
        result = await enrich_gap_followup("s1", "some question")
        assert result == "some question"
