from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite

from maelstrom.db import session_repo


async def create_chat_message(
    db: aiosqlite.Connection,
    session_id: str,
    role: str,
    content: str,
    citations_json: str = "[]",
    intent: str | None = None,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    mid = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO chat_messages (id, session_id, role, content, citations_json, created_at, intent) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (mid, session_id, role, content, citations_json, now, intent),
    )
    await db.commit()
    await session_repo.touch_session(db, session_id)
    return {
        "id": mid, "session_id": session_id, "role": role,
        "content": content, "citations_json": citations_json, "created_at": now,
        "intent": intent,
    }


async def list_messages_by_session(db: aiosqlite.Connection, session_id: str) -> list[dict]:
    cur = await db.execute(
        "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at", (session_id,)
    )
    return [dict(r) for r in await cur.fetchall()]


async def count_by_session(db: aiosqlite.Connection, session_id: str) -> int:
    cur = await db.execute("SELECT COUNT(*) FROM chat_messages WHERE session_id = ?", (session_id,))
    row = await cur.fetchone()
    return row[0] if row else 0


async def get_recent_intent(db: aiosqlite.Connection, session_id: str) -> str | None:
    """Return the most recent non-null intent for a session."""
    cur = await db.execute(
        "SELECT intent FROM chat_messages WHERE session_id = ? AND intent IS NOT NULL ORDER BY rowid DESC LIMIT 1",
        (session_id,),
    )
    row = await cur.fetchone()
    return row[0] if row else None
