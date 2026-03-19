"""topic_intake node — validate and normalize user topic input."""
from __future__ import annotations

from maelstrom.graph.gap_engine import GapEngineState

_MIN_LEN = 10
_MAX_LEN = 500


def topic_intake(state: GapEngineState) -> GapEngineState:
    """Validate topic, set error if invalid."""
    state["current_step"] = "topic_intake"
    topic = (state.get("topic") or "").strip()

    if not topic:
        state["error"] = "Topic is required"
        return state

    if len(topic) < _MIN_LEN:
        state["error"] = f"Topic too short (min {_MIN_LEN} characters)"
        return state

    if len(topic) > _MAX_LEN:
        topic = topic[:_MAX_LEN]

    state["topic"] = topic
    return state
