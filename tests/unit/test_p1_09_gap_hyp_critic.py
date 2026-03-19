"""P1-09: gap_hypothesis + gap_critic node tests."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from maelstrom.graph.gap_engine import GapEngineState
from maelstrom.graph.nodes.gap_hypothesis import gap_hypothesis, VALID_GAP_TYPES
from maelstrom.graph.nodes.gap_critic import gap_critic, VALID_VERDICTS

_PATCH_HYP = "maelstrom.graph.nodes.gap_hypothesis.call_llm"
_PATCH_CRIT = "maelstrom.graph.nodes.gap_critic.call_llm"


def _paper(pid: str) -> dict:
    return {"paper_id": pid, "title": f"Paper {pid}", "abstract": "Some abstract"}


SAMPLE_GAPS = [
    {"title": "Gap A", "summary": "Missing dataset coverage", "gap_type": "dataset",
     "evidence_refs": ["p1", "p2"], "confidence": 0.8},
    {"title": "Gap B", "summary": "No evaluation on X", "gap_type": "evaluation",
     "evidence_refs": ["p1"], "confidence": 0.6},
    {"title": "Gap C", "summary": "Method not applied to Y", "gap_type": "method",
     "evidence_refs": ["p2"], "confidence": 0.7},
    {"title": "Gap D", "summary": "Scale issue", "gap_type": "scale",
     "evidence_refs": ["p1", "p2"], "confidence": 0.5},
    {"title": "Gap E", "summary": "Domain gap", "gap_type": "domain",
     "evidence_refs": ["p1"], "confidence": 0.9},
]

SAMPLE_CRITIC = [
    {"gap_title": "Gap A", "verdict": "keep", "reasons": ["Novel", "Feasible"]},
    {"gap_title": "Gap B", "verdict": "revise", "reasons": ["Needs more evidence"]},
    {"gap_title": "Gap C", "verdict": "drop", "reasons": ["Already addressed"]},
    {"gap_title": "Gap D", "verdict": "keep", "reasons": ["Important"]},
    {"gap_title": "Gap E", "verdict": "keep", "reasons": ["High impact"]},
]
# --- gap_hypothesis tests ---

@pytest.mark.asyncio
async def test_hypothesis_count():
    with patch(_PATCH_HYP, new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = json.dumps(SAMPLE_GAPS)
        state: GapEngineState = {
            "papers": [_paper("p1"), _paper("p2")],
            "coverage_matrix": {"cells": {}, "summary": {}},
            "llm_config": {},
        }
        await gap_hypothesis(state)
    assert 5 <= len(state["gap_hypotheses"]) <= 15


@pytest.mark.asyncio
async def test_hypothesis_structure():
    with patch(_PATCH_HYP, new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = json.dumps(SAMPLE_GAPS)
        state: GapEngineState = {
            "papers": [_paper("p1"), _paper("p2")],
            "coverage_matrix": {"cells": {}, "summary": {}},
            "llm_config": {},
        }
        await gap_hypothesis(state)
    for g in state["gap_hypotheses"]:
        assert "title" in g
        assert "summary" in g
        assert "gap_type" in g
        assert "evidence_refs" in g
        assert "confidence" in g


@pytest.mark.asyncio
async def test_hypothesis_evidence_refs():
    with patch(_PATCH_HYP, new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = json.dumps(SAMPLE_GAPS)
        state: GapEngineState = {
            "papers": [_paper("p1"), _paper("p2")],
            "coverage_matrix": {"cells": {}, "summary": {}},
            "llm_config": {},
        }
        await gap_hypothesis(state)
    valid_ids = {"p1", "p2"}
    for g in state["gap_hypotheses"]:
        for ref in g["evidence_refs"]:
            assert ref in valid_ids


@pytest.mark.asyncio
async def test_hypothesis_gap_type():
    with patch(_PATCH_HYP, new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = json.dumps(SAMPLE_GAPS)
        state: GapEngineState = {
            "papers": [_paper("p1"), _paper("p2")],
            "coverage_matrix": {"cells": {}, "summary": {}},
            "llm_config": {},
        }
        await gap_hypothesis(state)
    for g in state["gap_hypotheses"]:
        assert g["gap_type"] in VALID_GAP_TYPES


@pytest.mark.asyncio
async def test_hypothesis_llm_error():
    with patch(_PATCH_HYP, new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = RuntimeError("LLM down")
        state: GapEngineState = {
            "papers": [_paper("p1")],
            "coverage_matrix": {"cells": {}, "summary": {}},
            "llm_config": {},
        }
        await gap_hypothesis(state)
    assert state["gap_hypotheses"] == []
    assert state.get("error") is not None


# --- gap_critic tests ---

@pytest.mark.asyncio
async def test_critic_verdict():
    with patch(_PATCH_CRIT, new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = json.dumps(SAMPLE_CRITIC)
        state: GapEngineState = {
            "gap_hypotheses": SAMPLE_GAPS,
            "papers": [_paper("p1"), _paper("p2")],
            "llm_config": {},
        }
        await gap_critic(state)
    for r in state["critic_results"]:
        assert "verdict" in r


@pytest.mark.asyncio
async def test_critic_verdict_values():
    with patch(_PATCH_CRIT, new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = json.dumps(SAMPLE_CRITIC)
        state: GapEngineState = {
            "gap_hypotheses": SAMPLE_GAPS,
            "papers": [_paper("p1"), _paper("p2")],
            "llm_config": {},
        }
        await gap_critic(state)
    for r in state["critic_results"]:
        assert r["verdict"] in VALID_VERDICTS


@pytest.mark.asyncio
async def test_critic_reasons():
    with patch(_PATCH_CRIT, new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = json.dumps(SAMPLE_CRITIC)
        state: GapEngineState = {
            "gap_hypotheses": SAMPLE_GAPS,
            "papers": [_paper("p1"), _paper("p2")],
            "llm_config": {},
        }
        await gap_critic(state)
    for r in state["critic_results"]:
        assert isinstance(r["reasons"], list)
        assert len(r["reasons"]) >= 1


@pytest.mark.asyncio
async def test_critic_all_gaps_reviewed():
    with patch(_PATCH_CRIT, new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = json.dumps(SAMPLE_CRITIC)
        state: GapEngineState = {
            "gap_hypotheses": SAMPLE_GAPS,
            "papers": [_paper("p1"), _paper("p2")],
            "llm_config": {},
        }
        await gap_critic(state)
    assert len(state["critic_results"]) == len(SAMPLE_GAPS)
