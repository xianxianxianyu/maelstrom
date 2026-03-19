"""citation_binding node — verify claim-abstract alignment and update confidence."""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any

from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

CONFIDENCE_PENALTY = 0.6

_ALIGNMENT_PROMPT = """You are a Citation Alignment Checker.
Given a paper abstract and claims extracted from it, verify whether each claim is supported by the abstract.

Paper title: {title}
Abstract: {abstract}

Claims:
{claims_json}

For each claim output:
[{{"claim_id": "...", "aligned": true, "source_span": "abstract, sentence N", "alignment_score": 0.8}}]

If a claim is NOT supported, set aligned=false and source_span="unverified"."""


async def _verify_group(
    paper: dict, claims: list[dict], llm_config: dict,
) -> dict[str, dict]:
    """Verify claims for one paper. Returns {claim_id: {aligned, source_span, alignment_score}}."""
    title = paper.get("title", "")
    abstract = paper.get("abstract", "")[:1000]
    claims_json = json.dumps(
        [{"claim_id": c["claim_id"], "text": c["text"]} for c in claims],
        ensure_ascii=False,
    )
    prompt = _ALIGNMENT_PROMPT.format(title=title, abstract=abstract, claims_json=claims_json)
    try:
        raw = await call_llm(prompt, llm_config, max_tokens=1024, timeout=30.0)
        parsed = json.loads(raw.strip())
        if isinstance(parsed, list):
            return {
                item["claim_id"]: {
                    "aligned": item.get("aligned", False),
                    "source_span": item.get("source_span", "unverified"),
                    "alignment_score": float(item.get("alignment_score", 0.0)),
                }
                for item in parsed if "claim_id" in item
            }
    except Exception as e:
        logger.warning("Citation binding failed for paper %s: %s", paper.get("paper_id"), e)
    return {}


async def citation_binding(state: dict) -> dict:
    state["current_step"] = "citation_binding"
    claims = state.get("claims", [])
    evidences = state.get("evidences", [])
    llm_config = state.get("llm_config", {})

    if not claims:
        return state

    # Build paper lookup from filtered_papers
    papers_by_id: dict[str, dict] = {}
    for p in state.get("filtered_papers", []):
        papers_by_id[p.get("paper_id", "")] = p

    # Group claims by paper_id
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in claims:
        groups[c.get("paper_id", "")].append(c)

    # Build evidence lookup
    evi_by_id: dict[str, dict] = {e["evidence_id"]: e for e in evidences}

    # Verify each group
    for paper_id, group_claims in groups.items():
        paper = papers_by_id.get(paper_id, {"paper_id": paper_id, "title": "", "abstract": ""})
        results = await _verify_group(paper, group_claims, llm_config)
        if not results:
            continue  # LLM failed, preserve originals
        for c in group_claims:
            cid = c["claim_id"]
            if cid not in results:
                continue
            r = results[cid]
            if not r["aligned"]:
                c["confidence"] = round(c.get("confidence", 0.5) * CONFIDENCE_PENALTY, 4)
                # Update evidence source_span
                for eid in c.get("evidence_refs", []):
                    if eid in evi_by_id:
                        evi_by_id[eid]["source_span"] = "unverified"
            else:
                for eid in c.get("evidence_refs", []):
                    if eid in evi_by_id:
                        evi_by_id[eid]["source_span"] = r["source_span"]

    state["claims"] = claims
    state["evidences"] = evidences
    return state
