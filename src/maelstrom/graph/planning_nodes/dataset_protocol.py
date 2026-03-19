"""dataset_protocol node — propose dataset selection and preprocessing protocol."""
from __future__ import annotations

import json
import logging
from typing import Any

from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

_DATASET_PROMPT = """You are a research planning assistant.
Given the hypothesis and baselines, propose a dataset selection and preprocessing protocol.

Hypothesis: {hypothesis}
Topic: {topic}
Baselines: {baselines_summary}

Output JSON:
{{
  "datasets": ["dataset1", "dataset2"],
  "preprocessing_steps": ["step1", "step2"],
  "split_strategy": "e.g. 80/10/10 train/val/test",
  "size_estimates": "estimated sizes"
}}"""


async def dataset_protocol(state: dict) -> dict:
    state["current_step"] = "dataset_protocol"
    llm_config = state.get("llm_config", {})

    baselines = state.get("baselines", {})
    baselines_summary = json.dumps(baselines, default=str, ensure_ascii=False)[:1500]

    prompt = _DATASET_PROMPT.format(
        hypothesis=state.get("hypothesis", ""),
        topic=state.get("topic", ""),
        baselines_summary=baselines_summary,
    )

    try:
        raw = await call_llm(prompt, llm_config, max_tokens=1024, timeout=60.0)
        parsed = json.loads(raw.strip())
        state["dataset_protocol"] = parsed
    except Exception as e:
        logger.warning("dataset_protocol LLM failed: %s", e)
        state["dataset_protocol"] = {"datasets": [], "preprocessing_steps": [], "split_strategy": "", "size_estimates": ""}

    return state
