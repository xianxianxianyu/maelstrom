"""Trace event repository — CRUD for trace_events table."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite


async def create_trace_event(
    db: aiosqlite.Connection,
    run_id: str,
    session_id: str,
    engine: str,
    event_type: str,
    node_name: str | None = None,
    payload_json: str = "{}",
) -> dict:
    tid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO trace_events (id, run_id, session_id, engine, event_type, node_name, timestamp, payload_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (tid, run_id, session_id, engine, event_type, node_name, now, payload_json),
    )
    await db.commit()
    return {"id": tid, "run_id": run_id, "session_id": session_id, "engine": engine,
            "event_type": event_type, "node_name": node_name, "timestamp": now, "payload_json": payload_json}


async def get_trace_event(db: aiosqlite.Connection, trace_id: str) -> dict | None:
    cur = await db.execute("SELECT * FROM trace_events WHERE id = ?", (trace_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def list_by_run(db: aiosqlite.Connection, run_id: str) -> list[dict]:
    cur = await db.execute(
        "SELECT * FROM trace_events WHERE run_id = ? ORDER BY timestamp", (run_id,)
    )
    return [dict(r) for r in await cur.fetchall()]


async def list_by_session(db: aiosqlite.Connection, session_id: str) -> list[dict]:
    cur = await db.execute(
        "SELECT * FROM trace_events WHERE session_id = ? ORDER BY timestamp", (session_id,)
    )
    return [dict(r) for r in await cur.fetchall()]


async def list_filtered(
    db: aiosqlite.Connection,
    *,
    run_id: str | None = None,
    session_id: str | None = None,
    engine: str | None = None,
    event_type: str | None = None,
    since: str | None = None,
    until: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> tuple[list[dict], int]:
    """Filtered + paginated query. Returns (rows, total_count)."""
    conditions: list[str] = []
    params: list[str | int] = []

    if run_id:
        conditions.append("run_id = ?")
        params.append(run_id)
    if session_id:
        conditions.append("session_id = ?")
        params.append(session_id)
    if engine:
        conditions.append("engine = ?")
        params.append(engine)
    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)
    if since:
        conditions.append("timestamp >= ?")
        params.append(since)
    if until:
        conditions.append("timestamp <= ?")
        params.append(until)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    # Total count
    cur = await db.execute(f"SELECT COUNT(*) FROM trace_events{where}", params)
    row = await cur.fetchone()
    total = row[0] if row else 0

    # Paginated rows
    cur = await db.execute(
        f"SELECT * FROM trace_events{where} ORDER BY timestamp LIMIT ? OFFSET ?",
        [*params, limit, offset],
    )
    rows = [dict(r) for r in await cur.fetchall()]
    return rows, total


async def session_stats(db: aiosqlite.Connection, session_id: str) -> dict:
    """Session-level aggregate stats: count by engine×event_type + time range."""
    cur = await db.execute(
        "SELECT engine, event_type, COUNT(*) as cnt FROM trace_events "
        "WHERE session_id = ? GROUP BY engine, event_type ORDER BY cnt DESC",
        (session_id,),
    )
    by_engine_type = [dict(r) for r in await cur.fetchall()]

    cur = await db.execute(
        "SELECT COUNT(*) as total, MIN(timestamp) as first_event, MAX(timestamp) as last_event "
        "FROM trace_events WHERE session_id = ?",
        (session_id,),
    )
    summary_row = await cur.fetchone()
    summary = dict(summary_row) if summary_row else {"total": 0, "first_event": None, "last_event": None}

    return {"summary": summary, "by_engine_type": by_engine_type}
