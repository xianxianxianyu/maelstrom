"""risk_estimation node — LLM generates RiskMemo."""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

_RISK_PROMPT = """You are a research planning assistant.
Assess risks for the following experiment plan.

Hypothesis: {hypothesis}
Topic: {topic}
Baselines count: {baseline_count}
Datasets: {datasets}
Metrics: {metrics}

Identify risks in categories: data, compute, methodology, timeline, other.
For each risk, assess severity (low/medium/high) and suggest mitigation.

Output JSON:
{{
  "risks": [
    {{"category": "data|compute|methodology|timeline|other", "description": "risk description", "severity": "low|medium|high", "mitigation": "mitigation strategy"}}
  ],
  "overall_risk_level": "low|medium|high",
  "recommendation": "overall recommendation"
}}"""


async def risk_estimation(state: dict) -> dict:
    state["current_step"] = "risk_estimation"
    llm_config = state.get("llm_config", {})

    ds = state.get("dataset_protocol", {})
    datasets = ds.get("datasets", []) if isinstance(ds, dict) else []

    prompt = _RISK_PROMPT.format(
        hypothesis=state.get("hypothesis", ""),
        topic=state.get("topic", ""),
        baseline_count=len((state.get("baselines", {}) or {}).get("entries", [])),
        datasets=json.dumps(datasets, ensure_ascii=False),
        metrics=json.dumps([m.get("name", "") if isinstance(m, dict) else str(m) for m in state.get("metrics", [])], ensure_ascii=False),
    )

    try:
        raw = await call_llm(prompt, llm_config, max_tokens=1024, timeout=60.0)
        parsed = json.loads(raw.strip())
        parsed["memo_id"] = f"risk-{uuid.uuid4().hex[:8]}"
        state["risk_memo"] = parsed
    except Exception as e:
        logger.warning("risk_estimation LLM failed: %s", e)
        state["risk_memo"] = {"memo_id": f"risk-{uuid.uuid4().hex[:8]}", "risks": [], "overall_risk_level": "medium", "recommendation": ""}

    return state
