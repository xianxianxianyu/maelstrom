"""plan_rendering node — assemble final ExperimentPlan + ExecutionChecklist."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

_CHECKLIST_PROMPT = """You are a research planning assistant.
Generate an execution checklist for the following experiment plan.

Hypothesis: {hypothesis}
Baselines: {baselines_count} methods
Datasets: {datasets}
Metrics: {metrics}
Ablation components: {ablation_count}

Output JSON:
{{
  "items": [
    {{"step": "step description", "category": "setup|data|training|evaluation|analysis"}}
  ]
}}"""


async def plan_rendering(state: dict) -> dict:
    state["current_step"] = "plan_rendering"
    llm_config = state.get("llm_config", {})

    ds = state.get("dataset_protocol", {})
    datasets = ds.get("datasets", []) if isinstance(ds, dict) else []
    baselines = state.get("baselines", {}) or {}
    ablation = state.get("ablation", {}) or {}

    prompt = _CHECKLIST_PROMPT.format(
        hypothesis=state.get("hypothesis", ""),
        baselines_count=len(baselines.get("entries", [])),
        datasets=json.dumps(datasets, ensure_ascii=False),
        metrics=json.dumps([m.get("name", "") if isinstance(m, dict) else str(m) for m in state.get("metrics", [])], ensure_ascii=False),
        ablation_count=len(ablation.get("components", [])),
    )

    try:
        raw = await call_llm(prompt, llm_config, max_tokens=1024, timeout=60.0)
        parsed = json.loads(raw.strip())
        state["checklist"] = parsed
    except Exception as e:
        logger.warning("plan_rendering checklist LLM failed: %s", e)
        state["checklist"] = {"items": []}

    # Assemble final ExperimentPlan
    plan_id = f"plan-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()

    state["plan"] = {
        "plan_id": plan_id,
        "session_id": state.get("session_id", ""),
        "source_synthesis_id": state.get("source_synthesis_id"),
        "topic": state.get("topic", ""),
        "hypothesis": state.get("hypothesis", ""),
        "variables": state.get("variables", []),
        "baselines": baselines,
        "ablation": ablation,
        "dataset_protocol": ds,
        "metrics": state.get("metrics", []),
        "checklist": state.get("checklist", {"items": []}),
        "risk_memo": state.get("risk_memo"),
        "created_at": now,
    }

    return state
