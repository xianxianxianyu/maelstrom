"""claim_critique node — LLM evaluates whether claims hold up."""
from __future__ import annotations

import json
import logging
from typing import Any

from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

_CRITIQUE_PROMPT = """You are a critical research reviewer.
Given the claim verdicts from evidence binding, provide a deeper critique.

Claim verdicts: {verdicts}
Metrics results: {metrics}

For each verdict, refine the assessment. Consider:
1. Statistical significance
2. Potential confounders
3. Generalizability

Output JSON:
{{
  "critiqued_verdicts": [
    {{"claim_id": "id", "claim_text": "text", "supported": true, "reasoning": "refined reasoning"}}
  ]
}}"""


async def claim_critique(state: dict) -> dict:
    state["current_step"] = "claim_critique"
    llm_config = state.get("llm_config", {})

    verdicts = state.get("claim_verdicts", [])
    if not verdicts:
        return state

    prompt = _CRITIQUE_PROMPT.format(
        verdicts=json.dumps(verdicts, default=str, ensure_ascii=False)[:2000],
        metrics=json.dumps(state.get("normalized_metrics", []), default=str, ensure_ascii=False)[:1000],
    )

    try:
        raw = await call_llm(prompt, llm_config, max_tokens=1024, timeout=60.0)
        parsed = json.loads(raw.strip())
        critiqued = parsed.get("critiqued_verdicts", [])
        if critiqued:
            state["claim_verdicts"] = critiqued
            # Update conclusion with verdicts
            if state.get("conclusion"):
                state["conclusion"]["claim_verdicts"] = critiqued
    except Exception as e:
        logger.warning("claim_critique LLM failed: %s", e)

    return state
