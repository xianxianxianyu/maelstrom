"""gap_critic node — review gap hypotheses with LLM verdicts."""
from __future__ import annotations

import json
import logging

from maelstrom.graph.gap_engine import GapEngineState
from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

VALID_VERDICTS = {"keep", "revise", "drop"}

_CRITIC_PROMPT = """You are a research gap critic. Review each gap hypothesis for novelty, feasibility, and impact.

Paper summaries:
{paper_summaries}

Gap hypotheses to review:
{gaps_text}

For EACH gap, return a JSON object:
{{
  "gap_title": "the gap's title",
  "verdict": "keep" or "revise" or "drop",
  "reasons": ["reason 1", "reason 2"]
}}

Return ONLY a JSON array of review objects."""


async def gap_critic(state: GapEngineState) -> GapEngineState:
    """Review each gap hypothesis with LLM verdict."""
    state["current_step"] = "gap_critic"
    hypotheses = state.get("gap_hypotheses", [])
    papers = state.get("papers", [])
    llm_config = state.get("llm_config", {})

    if not hypotheses:
        state["critic_results"] = []
        return state

    # Build context
    paper_summaries = ""
    for p in papers[:20]:
        pid = p.get("paper_id", "")
        title = p.get("title", "")
        abstract = (p.get("abstract") or "")[:200]
        paper_summaries += f"[{pid}] {title}: {abstract}\n"

    gaps_text = ""
    for i, g in enumerate(hypotheses):
        gaps_text += f"\n{i+1}. [{g.get('gap_type', 'other')}] {g.get('title', '')}\n   {g.get('summary', '')}\n   Evidence: {g.get('evidence_refs', [])}\n"

    prompt = _CRITIC_PROMPT.format(
        paper_summaries=paper_summaries,
        gaps_text=gaps_text,
    )

    try:
        raw = await call_llm(prompt, llm_config, temperature_override=0.3)
        parsed = json.loads(raw.strip())
        if not isinstance(parsed, list):
            parsed = []
    except Exception as e:
        logger.warning("Gap critic LLM failed: %s", e)
        # Fallback: keep all gaps
        state["critic_results"] = [
            {"gap_title": g.get("title", ""), "verdict": "keep", "reasons": ["Critic unavailable"]}
            for g in hypotheses
        ]
        return state

    # Validate and clean
    results = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        verdict = item.get("verdict", "keep")
        if verdict not in VALID_VERDICTS:
            verdict = "keep"
        reasons = item.get("reasons", [])
        if not isinstance(reasons, list):
            reasons = [str(reasons)]
        results.append({
            "gap_title": item.get("gap_title", ""),
            "verdict": verdict,
            "reasons": reasons,
        })

    state["critic_results"] = results
    return state
