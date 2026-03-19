"""ranking_packaging node — filter, score, rank gaps and generate TopicCandidates."""
from __future__ import annotations

import json
import logging
from typing import Any

from maelstrom.graph.gap_engine import GapEngineState
from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

_SCORING_PROMPT = """You are a research gap evaluator. Score each gap on three dimensions (0.0 to 1.0):
- novelty: how novel/unexplored is this gap
- feasibility: how feasible is it to address this gap
- impact: potential research impact if addressed

Gaps to score:
{gaps_text}

Return a JSON array where each element is:
{{"title": "gap title", "novelty": 0.0-1.0, "feasibility": 0.0-1.0, "impact": 0.0-1.0,
  "recommended_next_step": "brief suggestion", "risk_summary": "brief risk"}}

Return ONLY valid JSON."""


def _clamp(v: Any) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.5


async def ranking_packaging(state: GapEngineState) -> GapEngineState:
    """Filter dropped gaps, score, rank, and generate TopicCandidates."""
    state["current_step"] = "ranking_packaging"
    hypotheses = state.get("gap_hypotheses", [])
    critic_results = state.get("critic_results", [])
    llm_config = state.get("llm_config", {})

    # Build verdict lookup by title
    verdict_map: dict[str, str] = {}
    for cr in critic_results:
        verdict_map[cr.get("gap_title", "")] = cr.get("verdict", "keep")

    # Filter: remove dropped gaps
    kept = []
    for g in hypotheses:
        v = verdict_map.get(g.get("title", ""), "keep")
        if v != "drop":
            kept.append(g)

    if not kept:
        state["ranked_gaps"] = []
        state["topic_candidates"] = []
        return state

    # Score via LLM
    gaps_text = ""
    for i, g in enumerate(kept):
        gaps_text += f"\n{i+1}. [{g.get('gap_type', 'other')}] {g.get('title', '')}\n   {g.get('summary', '')}\n"

    scores_map: dict[str, dict] = {}
    try:
        prompt = _SCORING_PROMPT.format(gaps_text=gaps_text)
        raw = await call_llm(prompt, llm_config, temperature_override=0.3)
        parsed = json.loads(raw.strip())
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    scores_map[item.get("title", "")] = item
    except Exception as e:
        logger.warning("Scoring LLM failed: %s", e)

    # Build ranked_gaps with scores
    ranked = []
    for g in kept:
        title = g.get("title", "")
        sc = scores_map.get(title, {})
        novelty = _clamp(sc.get("novelty", 0.5))
        feasibility = _clamp(sc.get("feasibility", 0.5))
        impact = _clamp(sc.get("impact", 0.5))
        confidence = g.get("confidence", 0.5)
        weighted = confidence * (novelty * 0.4 + feasibility * 0.3 + impact * 0.3)

        ranked.append({
            **g,
            "scores": {"novelty": novelty, "feasibility": feasibility, "impact": impact},
            "weighted_score": round(weighted, 4),
            "recommended_next_step": sc.get("recommended_next_step", ""),
            "risk_summary": sc.get("risk_summary", ""),
        })

    ranked.sort(key=lambda x: x["weighted_score"], reverse=True)
    state["ranked_gaps"] = ranked

    # Generate TopicCandidates from top gaps
    candidates = []
    for i, g in enumerate(ranked[:5]):
        candidates.append({
            "title": g.get("title", ""),
            "related_gap_ids": [g.get("title", "")],
            "recommended_next_step": g.get("recommended_next_step", ""),
            "risk_summary": g.get("risk_summary", ""),
            "scores": g.get("scores", {}),
        })

    state["topic_candidates"] = candidates
    return state
