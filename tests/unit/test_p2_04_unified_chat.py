"""P2-04: Unified chat entry + intent persistence tests."""
from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite
import pytest

from maelstrom.db.chat_repo import create_chat_message, get_recent_intent
from maelstrom.db.migrations import run_migrations


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


@pytest.mark.asyncio
async def test_intent_persisted(db):
    msg = await create_chat_message(db, "s1", "system", "routed", intent="gap_discovery")
    assert msg["intent"] == "gap_discovery"


@pytest.mark.asyncio
async def test_intent_null_by_default(db):
    msg = await create_chat_message(db, "s1", "user", "hello")
    assert msg["intent"] is None


@pytest.mark.asyncio
async def test_recent_intent_query(db):
    await create_chat_message(db, "s1", "system", "r1", intent="qa_chat")
    await create_chat_message(db, "s1", "system", "r2", intent="gap_discovery")
    recent = await get_recent_intent(db, "s1")
    assert recent == "gap_discovery"


@pytest.mark.asyncio
async def test_recent_intent_none(db):
    recent = await get_recent_intent(db, "s1")
    assert recent is None


@pytest.mark.asyncio
async def test_migration_idempotent(db):
    """Running migrations twice should not error."""
    await run_migrations(db)
    # Should still work
    msg = await create_chat_message(db, "s1", "user", "test", intent="config")
    assert msg["intent"] == "config"


@pytest.mark.asyncio
async def test_backward_compat_no_intent(db):
    """Old-style create_chat_message without intent should still work."""
    msg = await create_chat_message(db, "s1", "user", "question", citations_json='["ref1"]')
    assert msg["content"] == "question"
    assert msg["intent"] is None
