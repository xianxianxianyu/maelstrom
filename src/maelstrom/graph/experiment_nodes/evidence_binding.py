"""evidence_binding node — bind conclusions back to claims/evidence."""
from __future__ import annotations

import json
import logging
from typing import Any

from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

_BINDING_PROMPT = """You are a research analyst.
Given the conclusion and original claims, bind each finding back to supporting evidence.

Conclusion summary: {summary}
Key findings: {findings}
Original claims: {claims}

For each original claim, determine if the experiment results support it.
Output JSON:
{{
  "bindings": [
    {{"claim_id": "id", "claim_text": "text", "supported": true, "reasoning": "why"}}
  ]
}}"""


async def evidence_binding(state: dict) -> dict:
    state["current_step"] = "evidence_binding"
    llm_config = state.get("llm_config", {})

    conclusion = state.get("conclusion", {}) or {}
    claims = state.get("claims", [])

    if not claims:
        state["claim_verdicts"] = []
        return state

    prompt = _BINDING_PROMPT.format(
        summary=conclusion.get("summary", ""),
        findings=json.dumps(conclusion.get("key_findings", []), ensure_ascii=False),
        claims=json.dumps(claims[:10], default=str, ensure_ascii=False)[:2000],
    )

    try:
        raw = await call_llm(prompt, llm_config, max_tokens=1024, timeout=60.0)
        parsed = json.loads(raw.strip())
        state["claim_verdicts"] = parsed.get("bindings", [])
    except Exception as e:
        logger.warning("evidence_binding LLM failed: %s", e)
        state["claim_verdicts"] = []

    return state
