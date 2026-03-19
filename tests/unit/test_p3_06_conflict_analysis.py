"""P3-06: Conflict Analysis node tests."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from maelstrom.graph.synthesis_nodes.conflict_analysis import conflict_analysis, _group_claims


def _claim(cid, problem="NER", method="BERT", text="claim text"):
    return {"claim_id": cid, "text": text, "claim_type": "method_effectiveness",
            "paper_id": "p1", "extracted_fields": {"problem": problem, "method": method}}


def _llm_response(consensus=None, conflicts=None, open_questions=None):
    return json.dumps({
        "consensus": consensus or [],
        "conflicts": conflicts or [],
        "open_questions": open_questions or [],
    })


@pytest.mark.asyncio
async def test_consensus_detected():
    resp = _llm_response(consensus=[
        {"statement": "BERT is effective for NER", "supporting_claim_ids": ["c1", "c2"], "strength": "strong"}
    ])
    with patch("maelstrom.graph.synthesis_nodes.conflict_analysis.call_llm", return_value=resp):
        state = {"claims": [_claim("c1"), _claim("c2")], "llm_config": {}}
        result = await conflict_analysis(state)
    assert len(result["consensus_points"]) == 1
    assert result["consensus_points"][0]["strength"] == "strong"


@pytest.mark.asyncio
async def test_conflict_detected():
    resp = _llm_response(conflicts=[
        {"statement": "Contradictory results", "claim_ids": ["c1", "c2"],
         "conflict_source": "dataset_difference", "requires_followup": False}
    ])
    with patch("maelstrom.graph.synthesis_nodes.conflict_analysis.call_llm", return_value=resp):
        state = {"claims": [_claim("c1"), _claim("c2")], "llm_config": {}}
        result = await conflict_analysis(state)
    assert len(result["conflict_points"]) == 1


@pytest.mark.asyncio
async def test_conflict_source_identified():
    resp = _llm_response(conflicts=[
        {"statement": "X", "claim_ids": ["c1", "c2"],
         "conflict_source": "metric_difference", "requires_followup": False}
    ])
    with patch("maelstrom.graph.synthesis_nodes.conflict_analysis.call_llm", return_value=resp):
        state = {"claims": [_claim("c1"), _claim("c2")], "llm_config": {}}
        result = await conflict_analysis(state)
    assert result["conflict_points"][0]["conflict_source"] == "metric_difference"


@pytest.mark.asyncio
async def test_requires_followup():
    resp = _llm_response(conflicts=[
        {"statement": "X", "claim_ids": ["c1", "c2"],
         "conflict_source": "dataset_difference", "requires_followup": True}
    ])
    with patch("maelstrom.graph.synthesis_nodes.conflict_analysis.call_llm", return_value=resp):
        state = {"claims": [_claim("c1"), _claim("c2")], "llm_config": {}}
        result = await conflict_analysis(state)
    assert result["conflict_points"][0]["requires_followup"] is True


@pytest.mark.asyncio
async def test_open_questions_generated():
    resp = _llm_response(open_questions=["What about low-resource?"])
    with patch("maelstrom.graph.synthesis_nodes.conflict_analysis.call_llm", return_value=resp):
        state = {"claims": [_claim("c1"), _claim("c2")], "llm_config": {}}
        result = await conflict_analysis(state)
    assert "What about low-resource?" in result["open_questions"]


def test_grouping_by_problem():
    claims = [
        _claim("c1", problem="NER"), _claim("c2", problem="NER"),
        _claim("c3", problem="QA"), _claim("c4", problem="QA"),
    ]
    groups = _group_claims(claims)
    assert len(groups) == 2
    group_sizes = sorted(len(g) for g in groups)
    assert group_sizes == [2, 2]


@pytest.mark.asyncio
async def test_llm_failure_empty():
    with patch("maelstrom.graph.synthesis_nodes.conflict_analysis.call_llm", side_effect=Exception("fail")):
        state = {"claims": [_claim("c1"), _claim("c2")], "llm_config": {}}
        result = await conflict_analysis(state)
    assert result["consensus_points"] == []
    assert result["conflict_points"] == []


@pytest.mark.asyncio
async def test_empty_claims():
    state = {"claims": [], "llm_config": {}}
    result = await conflict_analysis(state)
    assert result["consensus_points"] == []
    assert result["conflict_points"] == []
    assert result["open_questions"] == []
