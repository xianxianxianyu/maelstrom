"""Phase tracker — update and query session research phase."""
from __future__ import annotations

from datetime import datetime, timezone

from maelstrom.db.database import get_db
from maelstrom.schemas.common import ResearchPhase
from maelstrom.schemas.intent import ClassifiedIntent, IntentType


async def update_phase_on_route(session_id: str, intent: ClassifiedIntent) -> None:
    """Update session phase based on routing result."""
    db = await get_db()
    if intent.intent == IntentType.gap_discovery:
        await _set_phase(db, session_id, ResearchPhase.ideation)
    elif intent.intent == IntentType.planning:
        await _set_phase(db, session_id, ResearchPhase.planning)
    elif intent.intent == IntentType.experiment:
        await _set_phase(db, session_id, ResearchPhase.execution)


_ENGINE_PHASE_MAP: dict[str, ResearchPhase] = {
    "gap": ResearchPhase.ideation,
    "synthesis": ResearchPhase.grounding,
    "planning": ResearchPhase.planning,
    "experiment": ResearchPhase.execution,
}


async def advance_phase_on_completion(session_id: str, engine: str) -> None:
    """Advance session phase when an engine run completes.

    Maps engine → phase:
      gap → ideation, synthesis → grounding, planning → planning, experiment → execution
    Only advances forward (never goes backward).
    """
    target = _ENGINE_PHASE_MAP.get(engine)
    if not target:
        return
    current = await get_current_phase(session_id)
    phase_order = list(ResearchPhase)
    if phase_order.index(target) >= phase_order.index(current):
        db = await get_db()
        await _set_phase(db, session_id, target)


async def get_current_phase(session_id: str) -> ResearchPhase:
    db = await get_db()
    cur = await db.execute(
        "SELECT current_phase FROM sessions WHERE id = ?", (session_id,),
    )
    row = await cur.fetchone()
    if row and row[0]:
        try:
            return ResearchPhase(row[0])
        except ValueError:
            pass
    return ResearchPhase.ideation


async def _set_phase(db, session_id: str, phase: ResearchPhase) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE sessions SET current_phase = ?, phase_updated_at = ? WHERE id = ?",
        (phase.value, now, session_id),
    )
    await db.commit()
    try:
        from maelstrom.services.event_bus import get_event_bus
        bus = get_event_bus()
        await bus.emit("", "phase_started", {"phase": phase.value, "session_id": session_id}, session_id=session_id)
    except Exception:
        pass
