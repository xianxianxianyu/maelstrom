"""Policy repository — CRUD for policies table."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite


async def get_policy(db: aiosqlite.Connection, session_id: str) -> dict | None:
    cur = await db.execute("SELECT * FROM policies WHERE session_id = ?", (session_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def upsert_policy(
    db: aiosqlite.Connection, session_id: str, config_json: str,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    existing = await get_policy(db, session_id)
    if existing:
        await db.execute(
            "UPDATE policies SET config_json = ?, updated_at = ? WHERE session_id = ?",
            (config_json, now, session_id),
        )
        await db.commit()
        return {**existing, "config_json": config_json, "updated_at": now}
    pid = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO policies (id, session_id, config_json, updated_at) VALUES (?, ?, ?, ?)",
        (pid, session_id, config_json, now),
    )
    await db.commit()
    return {"id": pid, "session_id": session_id, "config_json": config_json, "updated_at": now}
