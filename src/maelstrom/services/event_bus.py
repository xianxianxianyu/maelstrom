"""Unified Event Bus — replaces per-service _emit/_event_queues."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from maelstrom.db.database import get_db

logger = logging.getLogger(__name__)


class EventBus:
    """Singleton event bus: SSE fan-out + trace persistence."""

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, run_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._queues.setdefault(run_id, []).append(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue) -> None:
        queues = self._queues.get(run_id, [])
        if q in queues:
            queues.remove(q)

    async def emit(
        self,
        run_id: str,
        event: str,
        data: dict,
        *,
        session_id: str = "",
        engine: str = "",
        node_name: str = "",
    ) -> None:
        payload = json.dumps(data, default=str)
        # 1. Push to SSE queues (synchronous, preserves existing behaviour)
        for q in self._queues.get(run_id, []):
            q.put_nowait({"event": event, "data": payload})
        # 2. Persist trace event (fire-and-forget, best-effort)
        if event != "__done__":
            asyncio.ensure_future(self._try_persist(
                run_id=run_id, session_id=session_id,
                engine=engine, event_type=event,
                node_name=node_name or None, payload_json=payload,
            ))

    async def _try_persist(self, **kwargs: Any) -> None:
        try:
            db = await get_db()
            await _persist_trace(db, **kwargs)
        except Exception:
            logger.debug("trace persist failed for %s/%s", kwargs.get("run_id"), kwargs.get("event_type"), exc_info=True)


async def _persist_trace(
    db: aiosqlite.Connection,
    *,
    run_id: str,
    session_id: str,
    engine: str,
    event_type: str,
    node_name: str | None,
    payload_json: str,
) -> None:
    tid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO trace_events (id, run_id, session_id, engine, event_type, node_name, timestamp, payload_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (tid, run_id, session_id, engine, event_type, node_name, now, payload_json),
    )
    await db.commit()


# ── Singleton ────────────────────────────────────────────────────────

_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def set_event_bus(bus: EventBus) -> None:
    global _bus
    _bus = bus
