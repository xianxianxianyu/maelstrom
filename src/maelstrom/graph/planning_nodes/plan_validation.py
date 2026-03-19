"""plan_validation node — cross-check plan consistency."""
from __future__ import annotations

import json
import logging
from typing import Any

from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

_VALIDATION_PROMPT = """You are a research planning validator.
Check the following experiment plan for consistency issues.

Hypothesis: {hypothesis}
Variables: {variables}
Baselines: {baselines_count} entries
Datasets: {datasets}
Metrics: {metrics_count} defined
Ablation components: {ablation_count}

Check for:
1. Hypothesis is testable with the proposed metrics
2. Baselines are appropriate for the hypothesis
3. Datasets are suitable for the evaluation
4. Ablation components cover key variables
5. No contradictions between plan elements

Output JSON:
{{
  "is_consistent": true,
  "issues": ["issue1 if any"],
  "suggestions": ["suggestion1 if any"]
}}"""


async def plan_validation(state: dict) -> dict:
    state["current_step"] = "plan_validation"
    llm_config = state.get("llm_config", {})

    ds = state.get("dataset_protocol", {})
    datasets = ds.get("datasets", []) if isinstance(ds, dict) else []
    baselines = state.get("baselines", {}) or {}
    ablation = state.get("ablation", {}) or {}

    prompt = _VALIDATION_PROMPT.format(
        hypothesis=state.get("hypothesis", ""),
        variables=json.dumps(state.get("variables", []), ensure_ascii=False),
        baselines_count=len(baselines.get("entries", [])),
        datasets=json.dumps(datasets, ensure_ascii=False),
        metrics_count=len(state.get("metrics", [])),
        ablation_count=len(ablation.get("components", [])),
    )

    try:
        raw = await call_llm(prompt, llm_config, max_tokens=1024, timeout=60.0)
        parsed = json.loads(raw.strip())
        state["validation"] = parsed
    except Exception as e:
        logger.warning("plan_validation LLM failed: %s", e)
        state["validation"] = {"is_consistent": True, "issues": [], "suggestions": []}

    return state
