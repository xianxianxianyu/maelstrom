"""coverage_matrix node — build task-method-dataset-metric coverage matrix."""
from __future__ import annotations

import json
import logging
from typing import Any

from maelstrom.graph.gap_engine import GapEngineState
from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

_BATCH_SIZE = 10

_EXTRACTION_PROMPT = """You are a research paper analyst. For each paper below, extract structured information.

Papers:
{papers_text}

For EACH paper, return a JSON object with:
- "paper_id": the paper's ID
- "tasks": list of research tasks addressed (e.g., "machine translation", "image classification")
- "methods": list of methods/models used (e.g., "Transformer", "BERT", "CNN")
- "datasets": list of datasets used (e.g., "ImageNet", "WMT14", "GLUE")
- "metrics": list of evaluation metrics (e.g., "BLEU", "accuracy", "F1")

Return a JSON array of these objects. If a field cannot be determined, use an empty list.
Return ONLY valid JSON, no explanation."""


async def _extract_batch(papers: list[dict], llm_config: dict[str, Any]) -> list[dict]:
    """Extract task/method/dataset/metric from a batch of papers via LLM."""
    papers_text = ""
    for i, p in enumerate(papers):
        pid = p.get("paper_id", f"paper_{i}")
        title = p.get("title", "")
        abstract = p.get("abstract", "")[:500]
        papers_text += f"\n[{pid}] {title}\n{abstract}\n"

    prompt = _EXTRACTION_PROMPT.format(papers_text=papers_text)
    try:
        raw = await call_llm(prompt, llm_config, temperature_override=0.3)
        parsed = json.loads(raw.strip())
        if isinstance(parsed, list):
            return parsed
    except Exception as e:
        logger.warning("LLM extraction failed for batch: %s", e)
    # Fallback: empty extractions
    return [{"paper_id": p.get("paper_id", ""), "tasks": [], "methods": [],
             "datasets": [], "metrics": []} for p in papers]


async def coverage_matrix(state: GapEngineState) -> GapEngineState:
    """Build coverage matrix from papers."""
    state["current_step"] = "coverage_matrix"
    papers = state.get("papers", [])
    llm_config = state.get("llm_config", {})

    if not papers:
        state["coverage_matrix"] = {"cells": {}, "summary": {
            "tasks": 0, "methods": 0, "datasets": 0, "metrics": 0,
            "filled_cells": 0, "total_cells": 0, "empty_cells_pct": 0.0,
        }}
        return state

    # Extract in batches
    all_extractions: list[dict] = []
    for i in range(0, len(papers), _BATCH_SIZE):
        batch = papers[i:i + _BATCH_SIZE]
        extractions = await _extract_batch(batch, llm_config)
        all_extractions.extend(extractions)

    # Build matrix
    cells: dict[str, list[str]] = {}
    all_tasks: set[str] = set()
    all_methods: set[str] = set()
    all_datasets: set[str] = set()
    all_metrics: set[str] = set()

    for ext in all_extractions:
        pid = ext.get("paper_id", "")
        tasks = ext.get("tasks", [])
        methods = ext.get("methods", [])
        datasets = ext.get("datasets", [])
        metrics = ext.get("metrics", [])

        all_tasks.update(tasks)
        all_methods.update(methods)
        all_datasets.update(datasets)
        all_metrics.update(metrics)

        for t in (tasks or [""]):
            for m in (methods or [""]):
                for d in (datasets or [""]):
                    for met in (metrics or [""]):
                        key = f"{t}|{m}|{d}|{met}"
                        if key not in cells:
                            cells[key] = []
                        if pid and pid not in cells[key]:
                            cells[key].append(pid)

    # Summary
    nt = max(len(all_tasks), 1)
    nm = max(len(all_methods), 1)
    nd = max(len(all_datasets), 1)
    nmet = max(len(all_metrics), 1)
    total_cells = nt * nm * nd * nmet
    filled = len([v for v in cells.values() if v])
    empty_pct = round((1 - filled / total_cells) * 100, 1) if total_cells > 0 else 0.0

    state["coverage_matrix"] = {
        "cells": cells,
        "summary": {
            "tasks": len(all_tasks),
            "methods": len(all_methods),
            "datasets": len(all_datasets),
            "metrics": len(all_metrics),
            "filled_cells": filled,
            "total_cells": total_cells,
            "empty_cells_pct": empty_pct,
        },
    }
    return state
