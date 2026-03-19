"""baseline_generation node — generate BaselineMatrix from claims/papers."""
from __future__ import annotations

import json
import logging
from typing import Any

from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

_BASELINE_PROMPT = """You are a research planning assistant.
Given the hypothesis and existing claims from literature, identify baseline methods for comparison.

Hypothesis: {hypothesis}
Topic: {topic}
Claims summary: {claims_summary}

Output JSON:
{{
  "entries": [
    {{"name": "baseline name", "description": "brief description", "expected_performance": "expected range"}}
  ],
  "comparison_metrics": ["metric1", "metric2"]
}}"""


async def baseline_generation(state: dict) -> dict:
    state["current_step"] = "baseline_generation"
    llm_config = state.get("llm_config", {})

    claims = state.get("claims", [])
    claims_summary = json.dumps(claims[:10], default=str, ensure_ascii=False)[:2000]

    prompt = _BASELINE_PROMPT.format(
        hypothesis=state.get("hypothesis", ""),
        topic=state.get("topic", ""),
        claims_summary=claims_summary,
    )

    try:
        raw = await call_llm(prompt, llm_config, max_tokens=1024, timeout=60.0)
        parsed = json.loads(raw.strip())
        state["baselines"] = parsed
    except Exception as e:
        logger.warning("baseline_generation LLM failed: %s", e)
        state["baselines"] = {"entries": [], "comparison_metrics": []}

    return state
