"""claim_extraction node — structured Claim + Evidence extraction from papers."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

BATCH_SIZE = 5

_EXTRACTION_PROMPT = """You are a structured literature extractor.
Given the following paper, extract structured claims:

Paper: {title}
Abstract: {abstract}

Extract:
- problem: research problem
- method: method used
- dataset: dataset used
- metric: evaluation metric
- main_result: main result
- limitation: limitations

Constraints:
1. Only use provided content
2. Do not fabricate information
3. Set fields to null if not mentioned

Output JSON:
{{
  "claims": [
    {{
      "claim_type": "method_effectiveness|dataset_finding|metric_comparison|limitation|assumption|negative_result",
      "text": "claim description",
      "extracted_fields": {{"problem": "...", "method": "...", "dataset": "...", "metric": "...", "main_result": "...", "limitation": "..."}},
      "confidence": 0.0-1.0,
      "source_span": "abstract"
    }}
  ]
}}"""


def _short_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _extract_batch(papers: list[dict], llm_config: dict) -> tuple[list[dict], list[dict]]:
    """Extract claims and evidences from a batch of papers."""
    claims: list[dict] = []
    evidences: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    for paper in papers:
        pid = paper.get("paper_id", "")
        title = paper.get("title", "")
        abstract = paper.get("abstract", "")[:1000]
        prompt = _EXTRACTION_PROMPT.format(title=title, abstract=abstract)
        try:
            raw = await call_llm(prompt, llm_config, max_tokens=2048, timeout=60.0)
            parsed = json.loads(raw.strip())
            raw_claims = parsed.get("claims", []) if isinstance(parsed, dict) else []
            for rc in raw_claims:
                cid = _short_id("clm")
                eid = _short_id("evi")
                claim_type = rc.get("claim_type", "method_effectiveness")
                confidence = max(0.0, min(1.0, float(rc.get("confidence", 0.5))))
                claim = {
                    "claim_id": cid,
                    "paper_id": pid,
                    "claim_type": claim_type,
                    "text": rc.get("text", ""),
                    "evidence_refs": [eid],
                    "confidence": confidence,
                    "extracted_fields": rc.get("extracted_fields", {}),
                }
                evidence = {
                    "evidence_id": eid,
                    "source_id": pid,
                    "source_span": rc.get("source_span", "abstract"),
                    "snippet": rc.get("text", ""),
                    "modality": "text",
                    "retrieved_via": "llm_extraction",
                    "created_at": now,
                }
                claims.append(claim)
                evidences.append(evidence)
        except Exception as e:
            logger.warning("Claim extraction failed for paper %s: %s", pid, e)
    return claims, evidences


async def claim_extraction(state: dict) -> dict:
    state["current_step"] = "claim_extraction"
    papers = state.get("filtered_papers", [])
    llm_config = state.get("llm_config", {})

    all_claims: list[dict] = []
    all_evidences: list[dict] = []

    if not papers:
        state["claims"] = []
        state["evidences"] = []
        return state

    # Process in batches sequentially
    batches = [papers[i:i + BATCH_SIZE] for i in range(0, len(papers), BATCH_SIZE)]
    for batch in batches:
        claims, evidences = await _extract_batch(batch, llm_config)
        all_claims.extend(claims)
        all_evidences.extend(evidences)

    state["claims"] = all_claims
    state["evidences"] = all_evidences
    return state
