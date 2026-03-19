"""reflection_summary node — generate ReflectionNote, identify new gaps."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

_REFLECTION_PROMPT = """You are a research reflection assistant.
Given the experiment conclusion and claim verdicts, generate a reflection.

Conclusion: {conclusion}
Claim verdicts: {verdicts}
Topic: {topic}

Generate:
1. Key insights from the experiment
2. New research gaps identified
3. Methodology notes for improvement
4. Suggested next steps

Output JSON:
{{
  "insights": ["insight1", "insight2"],
  "new_gaps": ["gap1", "gap2"],
  "methodology_notes": ["note1"],
  "next_steps": ["step1", "step2"]
}}"""


async def reflection_summary(state: dict) -> dict:
    state["current_step"] = "reflection_summary"
    llm_config = state.get("llm_config", {})

    conclusion = state.get("conclusion", {}) or {}

    prompt = _REFLECTION_PROMPT.format(
        conclusion=json.dumps(conclusion, default=str, ensure_ascii=False)[:2000],
        verdicts=json.dumps(state.get("claim_verdicts", []), default=str, ensure_ascii=False)[:1000],
        topic=state.get("topic", ""),
    )

    now = datetime.now(timezone.utc).isoformat()
    try:
        raw = await call_llm(prompt, llm_config, max_tokens=1024, timeout=60.0)
        parsed = json.loads(raw.strip())
        state["reflection"] = {
            "note_id": f"refl-{uuid.uuid4().hex[:8]}",
            "session_id": state.get("session_id", ""),
            "insights": parsed.get("insights", []),
            "new_gaps": parsed.get("new_gaps", []),
            "methodology_notes": parsed.get("methodology_notes", []),
            "next_steps": parsed.get("next_steps", []),
            "created_at": now,
        }
    except Exception as e:
        logger.warning("reflection_summary LLM failed: %s", e)
        state["reflection"] = {
            "note_id": f"refl-{uuid.uuid4().hex[:8]}",
            "session_id": state.get("session_id", ""),
            "insights": [],
            "new_gaps": [],
            "methodology_notes": [],
            "next_steps": [],
            "created_at": now,
        }

    return state
