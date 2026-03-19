from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite


async def create_artifact(
    db: aiosqlite.Connection, session_id: str, artifact_type: str, data_json: str = "{}"
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    aid = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO artifacts (id, session_id, type, data_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (aid, session_id, artifact_type, data_json, now),
    )
    await db.commit()
    return {"id": aid, "session_id": session_id, "type": artifact_type, "data_json": data_json, "created_at": now}


async def get_artifact(db: aiosqlite.Connection, artifact_id: str) -> dict | None:
    cur = await db.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def list_artifacts_by_session(db: aiosqlite.Connection, session_id: str) -> list[dict]:
    cur = await db.execute(
        "SELECT * FROM artifacts WHERE session_id = ? ORDER BY created_at", (session_id,)
    )
    return [dict(r) for r in await cur.fetchall()]


async def list_artifacts_by_type(
    db: aiosqlite.Connection, session_id: str, artifact_type: str
) -> list[dict]:
    cur = await db.execute(
        "SELECT * FROM artifacts WHERE session_id = ? AND type = ? ORDER BY created_at",
        (session_id, artifact_type),
    )
    return [dict(r) for r in await cur.fetchall()]
