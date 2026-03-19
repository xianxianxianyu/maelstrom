"""HITL Manager — approval gate with asyncio.Future pause/resume."""
from __future__ import annotations

import asyncio
import json
import logging

import aiosqlite

from maelstrom.db import approval_repo
from maelstrom.services.event_bus import get_event_bus

logger = logging.getLogger(__name__)


class HitlManager:
    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future] = {}

    async def request_approval(
        self,
        db: aiosqlite.Connection,
        session_id: str,
        run_id: str,
        approval_type: str,
        payload: dict | None = None,
    ) -> str:
        """Create approval record and block until resolved. Returns resolution decision."""
        payload_json = json.dumps(payload or {}, default=str)
        record = await approval_repo.create_approval(db, session_id, run_id, approval_type, payload_json)
        approval_id = record["id"]

        bus = get_event_bus()
        await bus.emit(
            run_id, "approval_requested",
            {"approval_id": approval_id, "approval_type": approval_type, "payload": payload or {}},
            session_id=session_id, engine=approval_type,
        )

        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[approval_id] = future

        try:
            resolution = await future
        finally:
            self._pending.pop(approval_id, None)

        return resolution

    async def resolve_approval(
        self,
        db: aiosqlite.Connection,
        approval_id: str,
        decision: str,
        resolved_by: str = "",
    ) -> dict | None:
        """Resolve a pending approval and unblock the waiting engine."""
        record = await approval_repo.resolve(db, approval_id, decision, resolved_by)
        if not record:
            return None

        bus = get_event_bus()
        await bus.emit(
            record["run_id"], "approval_resolved",
            {"approval_id": approval_id, "decision": decision},
            session_id=record["session_id"], engine=record["approval_type"],
        )

        future = self._pending.get(approval_id)
        if future and not future.done():
            future.set_result(decision)

        return record


# ── Singleton ────────────────────────────────────────────────────────

_manager: HitlManager | None = None


def get_hitl_manager() -> HitlManager:
    global _manager
    if _manager is None:
        _manager = HitlManager()
    return _manager
