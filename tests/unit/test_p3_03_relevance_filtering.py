"""P3-03: Relevance Filtering node tests."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from maelstrom.graph.synthesis_nodes.relevance_filtering import relevance_filtering


def _paper(pid, title="Paper"):
    return {"paper_id": pid, "title": title, "abstract": "some abstract"}


def _llm_scores(scores: dict[str, float]) -> str:
    return json.dumps([{"paper_id": k, "relevance": v, "reason": "ok"} for k, v in scores.items()])


@pytest.mark.asyncio
async def test_filter_removes_irrelevant():
    scores = {"p1": 0.9, "p2": 0.8, "p3": 0.7, "p4": 0.2, "p5": 0.1}
    papers = [_paper(pid) for pid in scores]
    with patch("maelstrom.graph.synthesis_nodes.relevance_filtering.call_llm", return_value=_llm_scores(scores)):
        state = {"targeted_papers": papers, "topic": "NER", "llm_config": {}}
        result = await relevance_filtering(state)
    assert len(result["filtered_papers"]) == 3


@pytest.mark.asyncio
async def test_filter_keeps_relevant():
    scores = {"p1": 0.9, "p2": 0.8, "p3": 0.7}
    papers = [_paper(pid) for pid in scores]
    with patch("maelstrom.graph.synthesis_nodes.relevance_filtering.call_llm", return_value=_llm_scores(scores)):
        state = {"targeted_papers": papers, "topic": "NER", "llm_config": {}}
        result = await relevance_filtering(state)
    assert len(result["filtered_papers"]) == 3


@pytest.mark.asyncio
async def test_filter_batch_processing():
    # 25 papers → 3 batches (10+10+5)
    scores = {f"p{i}": 0.8 for i in range(25)}
    papers = [_paper(f"p{i}") for i in range(25)]
    call_count = 0

    async def mock_llm(prompt, config, **kw):
        nonlocal call_count
        call_count += 1
        # Parse which papers are in this batch from the prompt
        batch_papers = json.loads(prompt.split("Return ONLY")[0].split("\n")[-2])
        batch_scores = {p["paper_id"]: 0.8 for p in batch_papers}
        return _llm_scores(batch_scores)

    with patch("maelstrom.graph.synthesis_nodes.relevance_filtering.call_llm", side_effect=mock_llm):
        state = {"targeted_papers": papers, "topic": "NER", "llm_config": {}}
        result = await relevance_filtering(state)
    assert call_count == 3
    assert len(result["filtered_papers"]) == 25


@pytest.mark.asyncio
async def test_filter_llm_failure_fallback():
    papers = [_paper(f"p{i}") for i in range(5)]
    with patch("maelstrom.graph.synthesis_nodes.relevance_filtering.call_llm", side_effect=Exception("LLM down")):
        state = {"targeted_papers": papers, "topic": "NER", "llm_config": {}}
        result = await relevance_filtering(state)
    # All papers kept on failure
    assert len(result["filtered_papers"]) == 5


@pytest.mark.asyncio
async def test_filter_too_few_lowers_threshold():
    # All papers score between 0.2 and 0.4 → default threshold filters all, lowered threshold keeps them
    scores = {"p1": 0.35, "p2": 0.3, "p3": 0.25, "p4": 0.9}
    papers = [_paper(pid) for pid in scores]
    with patch("maelstrom.graph.synthesis_nodes.relevance_filtering.call_llm", return_value=_llm_scores(scores)):
        state = {"targeted_papers": papers, "topic": "NER", "llm_config": {}}
        result = await relevance_filtering(state)
    # Default threshold: only p4 passes (1 < 3), so lower to 0.2 → p1,p2,p3,p4 all pass
    assert len(result["filtered_papers"]) == 4


@pytest.mark.asyncio
async def test_filter_empty_input():
    state = {"targeted_papers": [], "topic": "NER", "llm_config": {}}
    result = await relevance_filtering(state)
    assert result["filtered_papers"] == []
