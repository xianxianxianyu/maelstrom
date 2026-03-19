"""report_assembly node — assemble ReviewReport + persist + EvidenceMemory writeback."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from maelstrom.services.llm_client import call_llm
from maelstrom.services.evidence_memory import get_evidence_memory

logger = logging.getLogger(__name__)

_SUMMARY_PROMPT = """You are a research review writer.
Generate an executive summary (150-300 words) based on:

Research topic: {topic}
Papers analyzed: {paper_count}
Claims extracted: {claim_count}
Consensus points: {consensus_summary}
Conflict points: {conflict_summary}
Feasibility verdict: {verdict}

Write a coherent summary covering main findings, key consensus, major conflicts, and feasibility conclusion."""

_DEFAULT_SUMMARY = "Executive summary could not be generated automatically. Please review the detailed claims, consensus points, and conflict points below."


async def _generate_summary(state: dict, llm_config: dict) -> str:
    topic = state.get("topic", "")
    claims = state.get("claims", [])
    consensus = state.get("consensus_points", [])
    conflicts = state.get("conflict_points", [])
    memo = state.get("feasibility_memo", {})

    consensus_summary = "; ".join(
        c.get("statement", "") if isinstance(c, dict) else str(c) for c in consensus[:5]
    ) or "None"
    conflict_summary = "; ".join(
        c.get("statement", "") if isinstance(c, dict) else str(c) for c in conflicts[:5]
    ) or "None"
    verdict = memo.get("verdict", "unknown") if isinstance(memo, dict) else "unknown"

    prompt = _SUMMARY_PROMPT.format(
        topic=topic, paper_count=len(state.get("filtered_papers", [])),
        claim_count=len(claims), consensus_summary=consensus_summary,
        conflict_summary=conflict_summary, verdict=verdict,
    )
    try:
        return await call_llm(prompt, llm_config, max_tokens=1024, timeout=30.0)
    except Exception as e:
        logger.warning("Executive summary generation failed: %s", e)
        return _DEFAULT_SUMMARY


async def report_assembly(state: dict) -> dict:
    state["current_step"] = "report_assembly"
    llm_config = state.get("llm_config", {})
    session_id = state.get("session_id", "")

    # Generate executive summary
    summary = await _generate_summary(state, llm_config)

    # Assemble report
    report = {
        "report_id": str(uuid.uuid4()),
        "session_id": session_id,
        "source_gap_id": state.get("source_gap_id"),
        "topic": state.get("topic", ""),
        "claims": state.get("claims", []),
        "evidences": state.get("evidences", []),
        "consensus_points": state.get("consensus_points", []),
        "conflict_points": state.get("conflict_points", []),
        "open_questions": state.get("open_questions", []),
        "paper_count": len(state.get("filtered_papers", [])),
        "executive_summary": summary,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    state["review_report"] = report

    # Write to EvidenceMemory
    try:
        mem = get_evidence_memory()
        await mem.ingest_text(
            session_id, "review", report["report_id"],
            f"Review: {report['topic']}", summary,
        )
        for claim in report["claims"]:
            cid = claim.get("claim_id", "")
            await mem.ingest_text(
                session_id, "claim", cid,
                f"Claim: {claim.get('text', '')[:80]}",
                f"{claim.get('text', '')}\nType: {claim.get('claim_type', '')}",
            )
    except Exception as e:
        logger.warning("EvidenceMemory writeback failed: %s", e)

    return state
