"""feasibility_review node — 4-dimension assessment + verdict."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

_FEASIBILITY_PROMPT = """You are a research feasibility reviewer.
Assess the feasibility of this research direction based on the synthesis results.

Research topic: {topic}
Gap description: {gap_summary}
Consensus points: {consensus_count}
Conflict points: {conflict_count}
Open questions: {open_questions}

Key claims summary:
{top_claims_summary}

Assess:
1. gap_validity: Is the gap genuinely valid? (1-2 sentences)
2. existing_progress: Is existing work close to solving it? (1-2 sentences)
3. resource_assessment: Are resource requirements reasonable? (1-2 sentences)
4. verdict: advance (worth pursuing) / revise (needs adjustment) / reject (not recommended)
5. reasoning: Overall reasoning (2-3 sentences)
6. confidence: 0.0-1.0

Output JSON:
{{
  "gap_validity": "...",
  "existing_progress": "...",
  "resource_assessment": "...",
  "verdict": "advance|revise|reject",
  "reasoning": "...",
  "confidence": 0.8
}}"""


def _default_memo(report_id: str) -> dict:
    return {
        "memo_id": str(uuid.uuid4()),
        "report_id": report_id,
        "verdict": "revise",
        "gap_validity": "Unable to assess automatically",
        "existing_progress": "Unable to assess automatically",
        "resource_assessment": "Unable to assess automatically",
        "reasoning": "Automatic assessment failed, manual review recommended",
        "confidence": 0.0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def feasibility_review(state: dict) -> dict:
    state["current_step"] = "feasibility_review"
    topic = state.get("topic", "")
    gap_info = state.get("gap_info")
    gap_summary = gap_info.get("summary", "") if gap_info else ""
    claims = state.get("claims", [])
    consensus = state.get("consensus_points", [])
    conflicts = state.get("conflict_points", [])
    open_questions = state.get("open_questions", [])
    llm_config = state.get("llm_config", {})
    report_id = state.get("run_id", str(uuid.uuid4()))

    top_claims = claims[:10]
    claims_summary = "\n".join(
        f"- [{c.get('claim_type', '')}] {c.get('text', '')[:100]}" for c in top_claims
    ) or "No claims extracted"

    prompt = _FEASIBILITY_PROMPT.format(
        topic=topic, gap_summary=gap_summary,
        consensus_count=len(consensus), conflict_count=len(conflicts),
        open_questions=json.dumps(open_questions[:5], ensure_ascii=False),
        top_claims_summary=claims_summary,
    )

    try:
        raw = await call_llm(prompt, llm_config, max_tokens=1024, timeout=30.0)
        parsed = json.loads(raw.strip())
        if isinstance(parsed, dict):
            verdict = parsed.get("verdict", "revise")
            if verdict not in ("advance", "revise", "reject"):
                verdict = "revise"
            confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.5))))
            memo = {
                "memo_id": str(uuid.uuid4()),
                "report_id": report_id,
                "verdict": verdict,
                "gap_validity": parsed.get("gap_validity", ""),
                "existing_progress": parsed.get("existing_progress", ""),
                "resource_assessment": parsed.get("resource_assessment", ""),
                "reasoning": parsed.get("reasoning", ""),
                "confidence": confidence,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            state["feasibility_memo"] = memo
            return state
    except Exception as e:
        logger.warning("Feasibility review failed: %s", e)

    state["feasibility_memo"] = _default_memo(report_id)
    return state
