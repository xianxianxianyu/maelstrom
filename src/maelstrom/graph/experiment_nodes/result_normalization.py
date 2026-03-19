"""result_normalization node — standardize metrics for comparison."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def result_normalization(state: dict) -> dict:
    state["current_step"] = "result_normalization"

    metrics = state.get("metrics", [])
    normalized = []
    for m in metrics:
        if isinstance(m, dict):
            val = m.get("value", 0)
            baseline = m.get("baseline_value")
            delta = (val - baseline) if baseline is not None else None
            pct_change = (delta / baseline * 100) if baseline and baseline != 0 else None
            normalized.append({
                **m,
                "delta": delta,
                "pct_change": round(pct_change, 2) if pct_change is not None else None,
            })
        else:
            normalized.append(m)

    state["normalized_metrics"] = normalized
    return state
