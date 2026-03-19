"""P3-07: Feasibility Review node tests."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from maelstrom.graph.synthesis_nodes.feasibility_review import feasibility_review


def _llm_response(verdict="advance", confidence=0.8):
    return json.dumps({
        "gap_validity": "The gap is valid",
        "existing_progress": "Partial progress exists",
        "resource_assessment": "Resources are reasonable",
        "verdict": verdict,
        "reasoning": "Overall assessment",
        "confidence": confidence,
    })


def _base_state(**kw):
    defaults = {
        "topic": "NER", "run_id": "r1", "llm_config": {},
        "claims": [{"claim_id": "c1", "text": "BERT works", "claim_type": "method_effectiveness"}],
        "consensus_points": [{"statement": "consensus"}],
        "conflict_points": [],
        "open_questions": [],
    }
    defaults.update(kw)
    return defaults


@pytest.mark.asyncio
async def test_feasibility_advance():
    with patch("maelstrom.graph.synthesis_nodes.feasibility_review.call_llm", return_value=_llm_response("advance")):
        result = await feasibility_review(_base_state())
    assert result["feasibility_memo"]["verdict"] == "advance"


@pytest.mark.asyncio
async def test_feasibility_revise():
    with patch("maelstrom.graph.synthesis_nodes.feasibility_review.call_llm", return_value=_llm_response("revise")):
        result = await feasibility_review(_base_state(conflict_points=[{"statement": "conflict"}] * 5))
    assert result["feasibility_memo"]["verdict"] == "revise"


@pytest.mark.asyncio
async def test_feasibility_reject():
    with patch("maelstrom.graph.synthesis_nodes.feasibility_review.call_llm", return_value=_llm_response("reject")):
        result = await feasibility_review(_base_state())
    assert result["feasibility_memo"]["verdict"] == "reject"


@pytest.mark.asyncio
async def test_feasibility_four_dimensions():
    with patch("maelstrom.graph.synthesis_nodes.feasibility_review.call_llm", return_value=_llm_response()):
        result = await feasibility_review(_base_state())
    memo = result["feasibility_memo"]
    assert memo["gap_validity"] != ""
    assert memo["existing_progress"] != ""
    assert memo["resource_assessment"] != ""
    assert memo["reasoning"] != ""


@pytest.mark.asyncio
async def test_feasibility_confidence_range():
    with patch("maelstrom.graph.synthesis_nodes.feasibility_review.call_llm", return_value=_llm_response(confidence=1.5)):
        result = await feasibility_review(_base_state())
    assert 0.0 <= result["feasibility_memo"]["confidence"] <= 1.0


@pytest.mark.asyncio
async def test_feasibility_llm_failure():
    with patch("maelstrom.graph.synthesis_nodes.feasibility_review.call_llm", side_effect=Exception("fail")):
        result = await feasibility_review(_base_state())
    memo = result["feasibility_memo"]
    assert memo["verdict"] == "revise"
    assert memo["confidence"] == 0.0


@pytest.mark.asyncio
async def test_feasibility_empty_input():
    with patch("maelstrom.graph.synthesis_nodes.feasibility_review.call_llm", return_value=_llm_response()):
        result = await feasibility_review(_base_state(claims=[], consensus_points=[], conflict_points=[]))
    assert result["feasibility_memo"]["verdict"] == "advance"
