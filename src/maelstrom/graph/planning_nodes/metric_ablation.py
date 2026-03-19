"""metric_ablation node — define evaluation metrics and ablation components."""
from __future__ import annotations

import json
import logging
from typing import Any

from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

_METRIC_ABLATION_PROMPT = """You are a research planning assistant.
Given the hypothesis, baselines, and dataset protocol, define evaluation metrics and ablation study components.

Hypothesis: {hypothesis}
Topic: {topic}
Baselines: {baselines_summary}
Dataset: {dataset_summary}

Output JSON:
{{
  "metrics": [
    {{"name": "metric name", "formula": "definition or formula", "higher_is_better": true}}
  ],
  "ablation": {{
    "components": [
      {{"component": "component name", "rationale": "why ablate this", "expected_impact": "expected effect"}}
    ],
    "control_description": "full model description"
  }}
}}"""


async def metric_ablation(state: dict) -> dict:
    state["current_step"] = "metric_ablation"
    llm_config = state.get("llm_config", {})

    prompt = _METRIC_ABLATION_PROMPT.format(
        hypothesis=state.get("hypothesis", ""),
        topic=state.get("topic", ""),
        baselines_summary=json.dumps(state.get("baselines", {}), default=str, ensure_ascii=False)[:1000],
        dataset_summary=json.dumps(state.get("dataset_protocol", {}), default=str, ensure_ascii=False)[:1000],
    )

    try:
        raw = await call_llm(prompt, llm_config, max_tokens=1024, timeout=60.0)
        parsed = json.loads(raw.strip())
        state["metrics"] = parsed.get("metrics", [])
        state["ablation"] = parsed.get("ablation", {"components": [], "control_description": ""})
    except Exception as e:
        logger.warning("metric_ablation LLM failed: %s", e)
        state["metrics"] = []
        state["ablation"] = {"components": [], "control_description": ""}

    return state
