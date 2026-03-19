"""P2-07: Session phase tracking tests."""
from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite
import pytest

from maelstrom.db.migrations import run_migrations
from maelstrom.schemas.common import ResearchPhase
from maelstrom.schemas.intent import ClassifiedIntent, IntentType
from maelstrom.services.phase_tracker import get_current_phase, update_phase_on_route


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await run_migrations(conn)
    now = datetime.now(timezone.utc).isoformat()
    await conn.execute(
        "INSERT INTO sessions (id, title, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("s1", "Test", "active", now, now),
    )
    await conn.commit()
    yield conn
    await conn.close()


def test_research_phase_enum():
    assert len(ResearchPhase) == 4
    expected = {"ideation", "grounding", "planning", "execution"}
    assert {p.value for p in ResearchPhase} == expected


@pytest.mark.asyncio
async def test_session_default_phase(db):
    cur = await db.execute("SELECT current_phase FROM sessions WHERE id = 's1'")
    row = await cur.fetchone()
    assert row[0] == "ideation"


@pytest.mark.asyncio
async def test_update_phase_on_gap(db):
    from unittest.mock import patch, AsyncMock
    intent = ClassifiedIntent(intent=IntentType.gap_discovery, confidence=0.85)

    with patch("maelstrom.services.phase_tracker.get_db", new_callable=AsyncMock, return_value=db):
        await update_phase_on_route("s1", intent)

    cur = await db.execute("SELECT current_phase FROM sessions WHERE id = 's1'")
    row = await cur.fetchone()
    assert row[0] == "ideation"


@pytest.mark.asyncio
async def test_get_current_phase(db):
    from unittest.mock import patch, AsyncMock

    with patch("maelstrom.services.phase_tracker.get_db", new_callable=AsyncMock, return_value=db):
        phase = await get_current_phase("s1")
        assert phase == ResearchPhase.ideation


@pytest.mark.asyncio
async def test_migration_existing_sessions(db):
    """Existing sessions should get default phase value."""
    cur = await db.execute("SELECT current_phase, phase_updated_at FROM sessions WHERE id = 's1'")
    row = await cur.fetchone()
    assert row[0] == "ideation"
    assert row[1] is None  # Not yet updated
