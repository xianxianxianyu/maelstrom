"""conflict_analysis node — consensus/conflict detection among claims."""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any

from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

MAX_GROUP_SIZE = 15

_CONFLICT_PROMPT = """You are a Research Conflict Analyzer.
Given multiple claims and their evidence, determine:
- Which claims support each other (consensus)
- Which claims directly conflict (conflict)
- Whether conflicts stem from dataset, metric, scenario, or assumption differences
- Which conflicts need additional experimental verification

Claims:
{claims_json}

Output JSON:
{{
  "consensus": [
    {{"statement": "...", "supporting_claim_ids": ["clm-001"], "strength": "strong|moderate|weak"}}
  ],
  "conflicts": [
    {{"statement": "...", "claim_ids": ["clm-002", "clm-005"], "conflict_source": "dataset_difference|metric_difference|scenario_difference|assumption_difference", "requires_followup": true}}
  ],
  "open_questions": ["..."]
}}"""


def _group_claims(claims: list[dict]) -> list[list[dict]]:
    """Group claims by problem/method field for comparison."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in claims:
        fields = c.get("extracted_fields", {})
        key = fields.get("problem", "") or fields.get("method", "") or "general"
        groups[key].append(c)

    result = []
    for group in groups.values():
        # Split large groups
        for i in range(0, len(group), MAX_GROUP_SIZE):
            result.append(group[i:i + MAX_GROUP_SIZE])
    return result


async def _analyze_group(claims: list[dict], llm_config: dict) -> dict:
    """Analyze one group of claims for consensus/conflicts."""
    claims_json = json.dumps(
        [{"claim_id": c["claim_id"], "text": c["text"], "claim_type": c.get("claim_type", ""),
          "paper_id": c.get("paper_id", ""), "extracted_fields": c.get("extracted_fields", {})}
         for c in claims],
        ensure_ascii=False,
    )
    prompt = _CONFLICT_PROMPT.format(claims_json=claims_json)
    try:
        raw = await call_llm(prompt, llm_config, max_tokens=2048, timeout=30.0)
        parsed = json.loads(raw.strip())
        if isinstance(parsed, dict):
            return {
                "consensus": parsed.get("consensus", []),
                "conflicts": parsed.get("conflicts", []),
                "open_questions": parsed.get("open_questions", []),
            }
    except Exception as e:
        logger.warning("Conflict analysis failed: %s", e)
    return {"consensus": [], "conflicts": [], "open_questions": []}


async def conflict_analysis(state: dict) -> dict:
    state["current_step"] = "conflict_analysis"
    claims = state.get("claims", [])
    llm_config = state.get("llm_config", {})

    all_consensus: list[dict] = []
    all_conflicts: list[dict] = []
    all_questions: list[str] = []

    if not claims:
        state["consensus_points"] = []
        state["conflict_points"] = []
        state["open_questions"] = []
        return state

    groups = _group_claims(claims)
    for group in groups:
        if len(group) < 2:
            continue  # Need at least 2 claims to compare
        result = await _analyze_group(group, llm_config)
        all_consensus.extend(result["consensus"])
        all_conflicts.extend(result["conflicts"])
        all_questions.extend(result["open_questions"])

    state["consensus_points"] = all_consensus
    state["conflict_points"] = all_conflicts
    state["open_questions"] = all_questions
    return state
