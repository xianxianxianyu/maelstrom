"""Approval repository — CRUD for approvals table."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite


async def create_approval(
    db: aiosqlite.Connection,
    session_id: str,
    run_id: str,
    approval_type: str,
    payload_json: str = "{}",
) -> dict:
    aid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO approvals (id, session_id, run_id, approval_type, status, payload_json, requested_at) "
        "VALUES (?, ?, ?, ?, 'pending', ?, ?)",
        (aid, session_id, run_id, approval_type, payload_json, now),
    )
    await db.commit()
    return {
        "id": aid, "session_id": session_id, "run_id": run_id,
        "approval_type": approval_type, "status": "pending",
        "payload_json": payload_json, "requested_at": now,
        "resolved_at": None, "resolved_by": None,
    }


async def get_approval(db: aiosqlite.Connection, approval_id: str) -> dict | None:
    cur = await db.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def list_pending(db: aiosqlite.Connection, session_id: str | None = None) -> list[dict]:
    if session_id:
        cur = await db.execute(
            "SELECT * FROM approvals WHERE status = 'pending' AND session_id = ? ORDER BY requested_at",
            (session_id,),
        )
    else:
        cur = await db.execute("SELECT * FROM approvals WHERE status = 'pending' ORDER BY requested_at")
    return [dict(r) for r in await cur.fetchall()]


async def list_all(
    db: aiosqlite.Connection, session_id: str | None = None, limit: int = 50,
) -> list[dict]:
    if session_id:
        cur = await db.execute(
            "SELECT * FROM approvals WHERE session_id = ? ORDER BY requested_at DESC LIMIT ?",
            (session_id, limit),
        )
    else:
        cur = await db.execute(
            "SELECT * FROM approvals ORDER BY requested_at DESC LIMIT ?", (limit,),
        )
    return [dict(r) for r in await cur.fetchall()]


async def resolve(
    db: aiosqlite.Connection, approval_id: str, status: str, resolved_by: str = "",
) -> dict | None:
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE approvals SET status = ?, resolved_at = ?, resolved_by = ? WHERE id = ?",
        (status, now, resolved_by, approval_id),
    )
    await db.commit()
    return await get_approval(db, approval_id)
