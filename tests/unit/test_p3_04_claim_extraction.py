"""P3-04: Claim Extraction node tests."""
from __future__ import annotations

import json
from unittest.mock import patch, AsyncMock

import pytest

from maelstrom.graph.synthesis_nodes.claim_extraction import claim_extraction


def _paper(pid, title="Paper", abstract="Some abstract about methods"):
    return {"paper_id": pid, "title": title, "abstract": abstract}


def _llm_response(claims):
    return json.dumps({"claims": claims})


def _claim_data(claim_type="method_effectiveness", text="BERT works", confidence=0.8):
    return {
        "claim_type": claim_type, "text": text, "confidence": confidence,
        "extracted_fields": {"problem": "NER", "method": "BERT"},
        "source_span": "abstract",
    }


@pytest.mark.asyncio
async def test_extraction_basic():
    resp = _llm_response([_claim_data(), _claim_data(text="CRF baseline")])
    with patch("maelstrom.graph.synthesis_nodes.claim_extraction.call_llm", return_value=resp):
        state = {"filtered_papers": [_paper("p1"), _paper("p2"), _paper("p3")], "llm_config": {}}
        result = await claim_extraction(state)
    assert len(result["claims"]) == 6  # 2 per paper × 3


@pytest.mark.asyncio
async def test_extraction_fields():
    resp = _llm_response([_claim_data()])
    with patch("maelstrom.graph.synthesis_nodes.claim_extraction.call_llm", return_value=resp):
        state = {"filtered_papers": [_paper("p1")], "llm_config": {}}
        result = await claim_extraction(state)
    claim = result["claims"][0]
    assert "problem" in claim["extracted_fields"]
    assert "method" in claim["extracted_fields"]
    assert claim["claim_type"] == "method_effectiveness"


@pytest.mark.asyncio
async def test_extraction_evidence_created():
    resp = _llm_response([_claim_data()])
    with patch("maelstrom.graph.synthesis_nodes.claim_extraction.call_llm", return_value=resp):
        state = {"filtered_papers": [_paper("p1")], "llm_config": {}}
        result = await claim_extraction(state)
    assert len(result["evidences"]) == 1
    evi = result["evidences"][0]
    assert evi["source_id"] == "p1"
    assert evi["evidence_id"] in result["claims"][0]["evidence_refs"]


@pytest.mark.asyncio
async def test_extraction_claim_types():
    claims_data = [
        _claim_data("method_effectiveness"),
        _claim_data("limitation", text="Limited data"),
    ]
    resp = _llm_response(claims_data)
    with patch("maelstrom.graph.synthesis_nodes.claim_extraction.call_llm", return_value=resp):
        state = {"filtered_papers": [_paper("p1")], "llm_config": {}}
        result = await claim_extraction(state)
    types = {c["claim_type"] for c in result["claims"]}
    assert "method_effectiveness" in types
    assert "limitation" in types


@pytest.mark.asyncio
async def test_extraction_batch():
    resp = _llm_response([_claim_data()])
    call_count = 0

    async def mock_llm(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return resp

    papers = [_paper(f"p{i}") for i in range(12)]
    with patch("maelstrom.graph.synthesis_nodes.claim_extraction.call_llm", side_effect=mock_llm):
        state = {"filtered_papers": papers, "llm_config": {}}
        result = await claim_extraction(state)
    assert call_count == 12  # one LLM call per paper
    assert len(result["claims"]) == 12


@pytest.mark.asyncio
async def test_extraction_llm_failure_skip():
    call_idx = 0

    async def mock_llm(*args, **kwargs):
        nonlocal call_idx
        call_idx += 1
        if call_idx == 2:
            raise Exception("LLM timeout")
        return _llm_response([_claim_data()])

    papers = [_paper(f"p{i}") for i in range(3)]
    with patch("maelstrom.graph.synthesis_nodes.claim_extraction.call_llm", side_effect=mock_llm):
        state = {"filtered_papers": papers, "llm_config": {}}
        result = await claim_extraction(state)
    # p2 failed, p1 and p3 succeeded
    assert len(result["claims"]) == 2


@pytest.mark.asyncio
async def test_extraction_empty_papers():
    state = {"filtered_papers": [], "llm_config": {}}
    result = await claim_extraction(state)
    assert result["claims"] == []
    assert result["evidences"] == []


@pytest.mark.asyncio
async def test_extraction_confidence_range():
    claims_data = [_claim_data(confidence=0.3), _claim_data(confidence=1.5)]  # 1.5 should be clamped
    resp = _llm_response(claims_data)
    with patch("maelstrom.graph.synthesis_nodes.claim_extraction.call_llm", return_value=resp):
        state = {"filtered_papers": [_paper("p1")], "llm_config": {}}
        result = await claim_extraction(state)
    for c in result["claims"]:
        assert 0.0 <= c["confidence"] <= 1.0
