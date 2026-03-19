"""gap_hypothesis node — generate gap hypotheses from coverage matrix."""
from __future__ import annotations

import json
import logging

from maelstrom.graph.gap_engine import GapEngineState
from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

VALID_GAP_TYPES = {"dataset", "evaluation", "method", "deployment_setting", "scale", "domain", "other"}

_HYPOTHESIS_PROMPT = """You are a research gap analyst. Given a coverage matrix and paper summaries, identify research gaps.

Coverage matrix summary:
{matrix_summary}

Empty or sparse areas in the matrix:
{sparse_cells}

Paper summaries (first 20):
{paper_summaries}

Generate {n} research gap hypotheses. Each gap should be a JSON object:
{{
  "title": "short descriptive title",
  "summary": "1-2 sentence description of the gap",
  "gap_type": one of {gap_types},
  "evidence_refs": ["paper_id1", "paper_id2"],
  "confidence": 0.0 to 1.0
}}

Return ONLY a JSON array of gap objects."""


async def gap_hypothesis(state: GapEngineState) -> GapEngineState:
    """Generate gap hypotheses from coverage matrix and papers."""
    state["current_step"] = "gap_hypothesis"
    papers = state.get("papers", [])
    cm = state.get("coverage_matrix", {})
    llm_config = state.get("llm_config", {})

    if not papers:
        state["gap_hypotheses"] = []
        return state

    # Build prompt context
    summary = json.dumps(cm.get("summary", {}), indent=2)
    cells = cm.get("cells", {})
    sparse = [k for k, v in cells.items() if len(v) <= 1][:20]
    sparse_text = "\n".join(sparse) if sparse else "No sparse cells identified"

    paper_summaries = ""
    paper_ids = set()
    for p in papers[:20]:
        pid = p.get("paper_id", "")
        paper_ids.add(pid)
        title = p.get("title", "")
        abstract = (p.get("abstract") or "")[:200]
        paper_summaries += f"[{pid}] {title}: {abstract}\n"

    n = min(max(len(papers), 5), 15)
    prompt = _HYPOTHESIS_PROMPT.format(
        matrix_summary=summary,
        sparse_cells=sparse_text,
        paper_summaries=paper_summaries,
        n=n,
        gap_types=", ".join(sorted(VALID_GAP_TYPES)),
    )

    try:
        raw = await call_llm(prompt, llm_config)
        parsed = json.loads(raw.strip())
        if not isinstance(parsed, list):
            parsed = []
    except Exception as e:
        logger.warning("Gap hypothesis generation failed: %s", e)
        state["error"] = f"Gap hypothesis LLM failed: {e}"
        state["gap_hypotheses"] = []
        return state

    # Validate and clean
    hypotheses = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        gap_type = item.get("gap_type", "other")
        if gap_type not in VALID_GAP_TYPES:
            gap_type = "other"
        refs = [r for r in item.get("evidence_refs", []) if r in paper_ids]
        hypotheses.append({
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "gap_type": gap_type,
            "evidence_refs": refs,
            "confidence": max(0.0, min(1.0, float(item.get("confidence", 0.5)))),
        })

    state["gap_hypotheses"] = hypotheses
    return state
