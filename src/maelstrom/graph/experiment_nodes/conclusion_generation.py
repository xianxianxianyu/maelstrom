"""conclusion_generation node — LLM generates Conclusion from metrics + plan."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

_CONCLUSION_PROMPT = """You are a research analyst.
Given the experiment results and plan, generate a conclusion.

Hypothesis: {hypothesis}
Metrics results: {metrics}
Topic: {topic}

Generate:
1. A summary of findings
2. Key findings list
3. Limitations

Output JSON:
{{
  "summary": "conclusion summary",
  "key_findings": ["finding1", "finding2"],
  "limitations": ["limitation1"]
}}"""


async def conclusion_generation(state: dict) -> dict:
    state["current_step"] = "conclusion_generation"
    llm_config = state.get("llm_config", {})
    config = state.get("config_snapshot", {})

    prompt = _CONCLUSION_PROMPT.format(
        hypothesis=config.get("hypothesis", ""),
        metrics=json.dumps(state.get("normalized_metrics", []), default=str, ensure_ascii=False),
        topic=state.get("topic", ""),
    )

    now = datetime.now(timezone.utc).isoformat()
    try:
        raw = await call_llm(prompt, llm_config, max_tokens=1024, timeout=60.0)
        parsed = json.loads(raw.strip())
        state["conclusion"] = {
            "conclusion_id": f"conc-{uuid.uuid4().hex[:8]}",
            "session_id": state.get("session_id", ""),
            "summary": parsed.get("summary", ""),
            "key_findings": parsed.get("key_findings", []),
            "claim_verdicts": [],
            "limitations": parsed.get("limitations", []),
            "created_at": now,
        }
    except Exception as e:
        logger.warning("conclusion_generation LLM failed: %s", e)
        state["conclusion"] = {
            "conclusion_id": f"conc-{uuid.uuid4().hex[:8]}",
            "session_id": state.get("session_id", ""),
            "summary": "Conclusion generation failed",
            "key_findings": [],
            "claim_verdicts": [],
            "limitations": [],
            "created_at": now,
        }

    return state
