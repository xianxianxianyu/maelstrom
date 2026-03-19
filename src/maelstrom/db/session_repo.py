from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite


async def create_session(
    db: aiosqlite.Connection, title: str = "Untitled Session"
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    sid = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO sessions (id, title, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (sid, title, "active", now, now),
    )
    await db.commit()
    return {"id": sid, "title": title, "status": "active", "created_at": now, "updated_at": now}


async def get_session(db: aiosqlite.Connection, session_id: str) -> dict | None:
    cur = await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def list_sessions(db: aiosqlite.Connection) -> list[dict]:
    cur = await db.execute("SELECT * FROM sessions ORDER BY updated_at DESC")
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def update_session(
    db: aiosqlite.Connection, session_id: str, **fields: str
) -> dict | None:
    existing = await get_session(db, session_id)
    if not existing:
        return None
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [session_id]
    await db.execute(f"UPDATE sessions SET {sets} WHERE id = ?", vals)
    await db.commit()
    return await get_session(db, session_id)


async def touch_session(db: aiosqlite.Connection, session_id: str) -> None:
    """Update updated_at to now. Silently no-op if session doesn't exist."""
    now = datetime.now(timezone.utc).isoformat()
    await db.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
    await db.commit()


async def delete_session(db: aiosqlite.Connection, session_id: str) -> bool:
    cur = await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    await db.commit()
    return cur.rowcount > 0


async def list_sessions_by_user(db: aiosqlite.Connection, user_id: str) -> list[dict]:
    cur = await db.execute(
        "SELECT * FROM sessions WHERE user_id = ? ORDER BY updated_at DESC", (user_id,)
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]
