"""paper_retrieval node — orchestrate PaperRetriever across expanded queries."""
from __future__ import annotations

import logging
from typing import Any

from maelstrom.graph.gap_engine import GapEngineState
from maelstrom.services.paper_retriever import PaperRetriever

logger = logging.getLogger(__name__)


async def paper_retrieval(
    state: GapEngineState, retriever: PaperRetriever | None = None
) -> GapEngineState:
    """Call PaperRetriever for each expanded query, merge results into state."""
    state["current_step"] = "paper_retrieval"
    queries = state.get("expanded_queries", [])
    if not queries:
        state["error"] = "No queries to search"
        state["raw_papers"] = []
        return state

    if retriever is None:
        state["error"] = "PaperRetriever not configured"
        state["raw_papers"] = []
        return state

    all_papers: list[dict] = []
    all_statuses: list[dict] = []
    any_success = False

    for query in queries:
        result = await retriever.search_with_fallback(query)
        for p in result.papers:
            all_papers.append(p.model_dump(mode="json"))
        for s in result.source_statuses:
            all_statuses.append(s.model_dump(mode="json"))
        if any(s.status == "ok" for s in result.source_statuses):
            any_success = True

    if not any_success:
        state["error"] = "All paper retrieval queries failed"

    state["raw_papers"] = all_papers
    state["search_result"] = {
        "total_papers": len(all_papers),
        "source_statuses": all_statuses,
    }
    return state
