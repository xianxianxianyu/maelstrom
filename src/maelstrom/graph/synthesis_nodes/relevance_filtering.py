"""relevance_filtering node — LLM batch relevance scoring + threshold filtering."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

BATCH_SIZE = 10
MAX_CONCURRENT = 3
DEFAULT_THRESHOLD = 0.4
LOW_THRESHOLD = 0.2
MIN_PAPERS = 3

_RELEVANCE_PROMPT = """You are a literature relevance assessor.
Research topic: {topic}
{gap_context}

Rate the relevance of each paper to this research topic (0.0-1.0):
{papers_json}

Return ONLY a JSON array:
[{{"paper_id": "...", "relevance": 0.0, "reason": "..."}}]"""


async def _score_batch(
    papers: list[dict], topic: str, gap_summary: str, llm_config: dict,
) -> dict[str, float]:
    """Score a batch of papers, return {paper_id: relevance}."""
    papers_json = json.dumps(
        [{"paper_id": p.get("paper_id", ""), "title": p.get("title", ""), "abstract": p.get("abstract", "")[:300]}
         for p in papers],
        ensure_ascii=False,
    )
    gap_context = f"Gap description: {gap_summary}" if gap_summary else ""
    prompt = _RELEVANCE_PROMPT.format(topic=topic, gap_context=gap_context, papers_json=papers_json)
    try:
        raw = await call_llm(prompt, llm_config, max_tokens=1024, timeout=30.0)
        parsed = json.loads(raw.strip())
        if isinstance(parsed, list):
            return {item["paper_id"]: float(item.get("relevance", 0.5)) for item in parsed if "paper_id" in item}
    except Exception as e:
        logger.warning("Relevance scoring failed for batch: %s", e)
    return {}


def _apply_filter(papers: list[dict], scores: dict[str, float], threshold: float) -> list[dict]:
    result = []
    for p in papers:
        pid = p.get("paper_id", "")
        score = scores.get(pid, 0.5)  # default keep if not scored
        if score >= threshold:
            result.append(p)
    return result


async def relevance_filtering(state: dict) -> dict:
    state["current_step"] = "relevance_filtering"
    papers = state.get("targeted_papers", [])
    topic = state.get("topic", "")
    gap_info = state.get("gap_info")
    gap_summary = gap_info.get("summary", "") if gap_info else ""
    llm_config = state.get("llm_config", {})

    if not papers:
        state["filtered_papers"] = []
        return state

    # Batch papers
    batches = [papers[i:i + BATCH_SIZE] for i in range(0, len(papers), BATCH_SIZE)]

    # Score batches with concurrency limit
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    all_scores: dict[str, float] = {}

    async def score_with_sem(batch):
        async with sem:
            return await _score_batch(batch, topic, gap_summary, llm_config)

    tasks = [score_with_sem(batch) for batch in batches]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    llm_failed = True
    for r in results:
        if isinstance(r, dict) and r:
            all_scores.update(r)
            llm_failed = False

    # Fallback: if all LLM calls failed, keep everything
    if llm_failed:
        state["filtered_papers"] = list(papers)
        return state

    # Apply threshold
    filtered = _apply_filter(papers, all_scores, DEFAULT_THRESHOLD)

    # If too few, lower threshold
    if len(filtered) < MIN_PAPERS and len(papers) >= MIN_PAPERS:
        filtered = _apply_filter(papers, all_scores, LOW_THRESHOLD)

    state["filtered_papers"] = filtered
    return state
