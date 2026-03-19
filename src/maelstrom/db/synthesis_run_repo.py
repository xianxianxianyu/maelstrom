"""Synthesis run DB repo — CRUD for synthesis_runs table."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite

from maelstrom.db import session_repo


async def create_synthesis_run(
    db: aiosqlite.Connection, session_id: str, topic: str, source_gap_id: str | None = None,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    rid = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO synthesis_runs (id, session_id, topic, source_gap_id, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (rid, session_id, topic, source_gap_id, "pending", now),
    )
    await db.commit()
    await session_repo.touch_session(db, session_id)
    return {
        "id": rid, "session_id": session_id, "topic": topic,
        "source_gap_id": source_gap_id, "status": "pending",
        "result_json": "{}", "created_at": now, "completed_at": None,
    }


async def get_synthesis_run(db: aiosqlite.Connection, run_id: str) -> dict | None:
    cur = await db.execute("SELECT * FROM synthesis_runs WHERE id = ?", (run_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def update_synthesis_run_status(
    db: aiosqlite.Connection, run_id: str, status: str,
) -> None:
    completed = datetime.now(timezone.utc).isoformat() if status in ("completed", "failed") else None
    if completed:
        await db.execute(
            "UPDATE synthesis_runs SET status = ?, completed_at = ? WHERE id = ?",
            (status, completed, run_id),
        )
    else:
        await db.execute("UPDATE synthesis_runs SET status = ? WHERE id = ?", (status, run_id))
    await db.commit()
    cur = await db.execute("SELECT session_id FROM synthesis_runs WHERE id = ?", (run_id,))
    row = await cur.fetchone()
    if row:
        await session_repo.touch_session(db, row[0])


async def update_synthesis_run_result(
    db: aiosqlite.Connection, run_id: str, result_json: str,
) -> None:
    await db.execute("UPDATE synthesis_runs SET result_json = ? WHERE id = ?", (result_json, run_id))
    await db.commit()


async def update_synthesis_run_progress(
    db: aiosqlite.Connection, run_id: str, current_step: str, progress_json: str,
) -> None:
    await db.execute(
        "UPDATE synthesis_runs SET current_step = ?, progress_json = ? WHERE id = ?",
        (current_step, progress_json, run_id),
    )
    await db.commit()


async def count_by_session(db: aiosqlite.Connection, session_id: str) -> int:
    cur = await db.execute("SELECT COUNT(*) FROM synthesis_runs WHERE session_id = ?", (session_id,))
    row = await cur.fetchone()
    return row[0] if row else 0


async def latest_by_session(db: aiosqlite.Connection, session_id: str) -> dict | None:
    cur = await db.execute(
        "SELECT * FROM synthesis_runs WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
        (session_id,),
    )
    row = await cur.fetchone()
    return dict(row) if row else None


async def list_by_session(
    db: aiosqlite.Connection, session_id: str, limit: int = 10,
) -> list[dict]:
    cur = await db.execute(
        "SELECT * FROM synthesis_runs WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
        (session_id, limit),
    )
    return [dict(r) for r in await cur.fetchall()]
