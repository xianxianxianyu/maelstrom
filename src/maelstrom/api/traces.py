"""Trace API — query persisted trace events."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from maelstrom.db import trace_event_repo
from maelstrom.db.database import get_db

router = APIRouter(prefix="/api/traces", tags=["traces"])


@router.get("/stats")
async def trace_stats(session_id: str):
    db = await get_db()
    result = await trace_event_repo.session_stats(db, session_id)
    return result


@router.get("")
async def list_traces(
    run_id: str | None = None,
    session_id: str | None = None,
    engine: str | None = None,
    event_type: str | None = None,
    since: str | None = None,
    until: str | None = None,
    offset: int = 0,
    limit: int = 100,
):
    db = await get_db()
    items, total = await trace_event_repo.list_filtered(
        db,
        run_id=run_id,
        session_id=session_id,
        engine=engine,
        event_type=event_type,
        since=since,
        until=until,
        offset=offset,
        limit=limit,
    )
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@router.get("/{trace_id}")
async def get_trace(trace_id: str):
    db = await get_db()
    event = await trace_event_repo.get_trace_event(db, trace_id)
    if not event:
        raise HTTPException(status_code=404, detail="Trace event not found")
    return event
