"""config_capture node — snapshot ExperimentPlan as frozen configuration."""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def config_capture(state: dict) -> dict:
    state["current_step"] = "config_capture"

    plan = state.get("plan", {}) or {}
    state["config_snapshot"] = {
        "plan_id": plan.get("plan_id", ""),
        "hypothesis": plan.get("hypothesis", ""),
        "variables": plan.get("variables", []),
        "baselines": plan.get("baselines", {}),
        "dataset_protocol": plan.get("dataset_protocol", {}),
        "metrics": plan.get("metrics", []),
        "ablation": plan.get("ablation", {}),
    }

    return state
