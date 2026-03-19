"""metrics_ingestion node — receive/simulate metrics input."""
from __future__ import annotations

import json
import logging
import random
from typing import Any

from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

_METRICS_PROMPT = """You are a research experiment simulator.
Given the experiment configuration, simulate realistic metric results.

Hypothesis: {hypothesis}
Metrics to evaluate: {metrics}
Baselines: {baselines}

For each metric, provide a simulated value for the proposed method and baseline.
Output JSON:
{{
  "metrics": [
    {{"name": "metric name", "value": 0.85, "baseline_value": 0.78, "is_improvement": true}}
  ]
}}"""


async def metrics_ingestion(state: dict) -> dict:
    state["current_step"] = "metrics_ingestion"
    llm_config = state.get("llm_config", {})
    config = state.get("config_snapshot", {})

    prompt = _METRICS_PROMPT.format(
        hypothesis=config.get("hypothesis", ""),
        metrics=json.dumps(config.get("metrics", []), default=str, ensure_ascii=False),
        baselines=json.dumps(config.get("baselines", {}), default=str, ensure_ascii=False)[:1000],
    )

    try:
        raw = await call_llm(prompt, llm_config, max_tokens=1024, timeout=60.0)
        parsed = json.loads(raw.strip())
        state["metrics"] = parsed.get("metrics", [])
    except Exception as e:
        logger.warning("metrics_ingestion LLM failed: %s", e)
        state["metrics"] = []

    return state
