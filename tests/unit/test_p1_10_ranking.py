"""P1-10: ranking_packaging node tests."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from maelstrom.graph.gap_engine import GapEngineState
from maelstrom.graph.nodes.ranking_packaging import ranking_packaging

_PATCH = "maelstrom.graph.nodes.ranking_packaging.call_llm"

GAPS = [
    {"title": "Gap A", "summary": "s", "gap_type": "dataset", "evidence_refs": [], "confidence": 0.9},
    {"title": "Gap B", "summary": "s", "gap_type": "method", "evidence_refs": [], "confidence": 0.7},
    {"title": "Gap C", "summary": "s", "gap_type": "evaluation", "evidence_refs": [], "confidence": 0.5},
]

CRITIC = [
    {"gap_title": "Gap A", "verdict": "keep", "reasons": ["good"]},
    {"gap_title": "Gap B", "verdict": "drop", "reasons": ["already done"]},
    {"gap_title": "Gap C", "verdict": "revise", "reasons": ["needs work"]},
]

SCORES = [
    {"title": "Gap A", "novelty": 0.9, "feasibility": 0.8, "impact": 0.7,
     "recommended_next_step": "Collect data", "risk_summary": "Low risk"},
    {"title": "Gap C", "novelty": 0.6, "feasibility": 0.5, "impact": 0.4,
     "recommended_next_step": "Revise scope", "risk_summary": "Medium risk"},
]


def _state() -> GapEngineState:
    return {
        "gap_hypotheses": GAPS,
        "critic_results": CRITIC,
        "llm_config": {},
    }


@pytest.mark.asyncio
async def test_filter_dropped():
    with patch(_PATCH, new_callable=AsyncMock) as m:
        m.return_value = json.dumps(SCORES)
        state = _state()
        await ranking_packaging(state)
    titles = [g["title"] for g in state["ranked_gaps"]]
    assert "Gap B" not in titles


@pytest.mark.asyncio
async def test_keep_kept():
    with patch(_PATCH, new_callable=AsyncMock) as m:
        m.return_value = json.dumps(SCORES)
        state = _state()
        await ranking_packaging(state)
    titles = [g["title"] for g in state["ranked_gaps"]]
    assert "Gap A" in titles
    assert "Gap C" in titles
@pytest.mark.asyncio
async def test_scores_range():
    with patch(_PATCH, new_callable=AsyncMock) as m:
        m.return_value = json.dumps(SCORES)
        state = _state()
        await ranking_packaging(state)
    for g in state["ranked_gaps"]:
        for dim in ("novelty", "feasibility", "impact"):
            assert 0.0 <= g["scores"][dim] <= 1.0


@pytest.mark.asyncio
async def test_ranking_order():
    with patch(_PATCH, new_callable=AsyncMock) as m:
        m.return_value = json.dumps(SCORES)
        state = _state()
        await ranking_packaging(state)
    scores = [g["weighted_score"] for g in state["ranked_gaps"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_topic_candidate_generated():
    with patch(_PATCH, new_callable=AsyncMock) as m:
        m.return_value = json.dumps(SCORES)
        state = _state()
        await ranking_packaging(state)
    assert len(state["topic_candidates"]) >= 1


@pytest.mark.asyncio
async def test_topic_candidate_refs():
    with patch(_PATCH, new_callable=AsyncMock) as m:
        m.return_value = json.dumps(SCORES)
        state = _state()
        await ranking_packaging(state)
    gap_titles = {g["title"] for g in state["ranked_gaps"]}
    for tc in state["topic_candidates"]:
        for ref in tc["related_gap_ids"]:
            assert ref in gap_titles


@pytest.mark.asyncio
async def test_topic_candidate_fields():
    with patch(_PATCH, new_callable=AsyncMock) as m:
        m.return_value = json.dumps(SCORES)
        state = _state()
        await ranking_packaging(state)
    for tc in state["topic_candidates"]:
        assert "title" in tc
        assert "related_gap_ids" in tc
        assert "recommended_next_step" in tc
        assert "risk_summary" in tc


@pytest.mark.asyncio
async def test_all_dropped():
    critic_all_drop = [
        {"gap_title": "Gap A", "verdict": "drop", "reasons": ["x"]},
        {"gap_title": "Gap B", "verdict": "drop", "reasons": ["x"]},
        {"gap_title": "Gap C", "verdict": "drop", "reasons": ["x"]},
    ]
    state: GapEngineState = {
        "gap_hypotheses": GAPS,
        "critic_results": critic_all_drop,
        "llm_config": {},
    }
    await ranking_packaging(state)
    assert state["ranked_gaps"] == []
    assert state["topic_candidates"] == []
