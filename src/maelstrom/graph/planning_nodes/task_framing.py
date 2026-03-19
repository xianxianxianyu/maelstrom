"""task_framing node — read ReviewReport + FeasibilityMemo, generate hypothesis + variables."""
from __future__ import annotations

import json
import logging
from typing import Any

from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

_FRAMING_PROMPT = """You are a research planning assistant.
Given the following synthesis review report and feasibility memo, generate:
1. A clear, testable hypothesis
2. A list of key independent/dependent variables

Review Report:
Topic: {topic}
Executive Summary: {executive_summary}
Open Questions: {open_questions}

Feasibility Memo:
Verdict: {verdict}
Reasoning: {reasoning}

Output JSON:
{{
  "hypothesis": "A clear testable hypothesis statement",
  "variables": ["variable1", "variable2", ...]
}}"""


async def task_framing(state: dict) -> dict:
    state["current_step"] = "task_framing"
    llm_config = state.get("llm_config", {})
    topic = state.get("topic", "")

    review = state.get("review_report", {}) or {}
    feasibility = state.get("feasibility_memo", {}) or {}

    prompt = _FRAMING_PROMPT.format(
        topic=topic,
        executive_summary=review.get("executive_summary", "N/A"),
        open_questions=json.dumps(review.get("open_questions", []), ensure_ascii=False),
        verdict=feasibility.get("verdict", "N/A"),
        reasoning=feasibility.get("reasoning", "N/A"),
    )

    try:
        raw = await call_llm(prompt, llm_config, max_tokens=1024, timeout=60.0)
        parsed = json.loads(raw.strip())
        state["hypothesis"] = parsed.get("hypothesis", "")
        state["variables"] = parsed.get("variables", [])
    except Exception as e:
        logger.warning("task_framing LLM failed: %s", e)
        state["hypothesis"] = f"Investigate: {topic}"
        state["variables"] = []

    return state
