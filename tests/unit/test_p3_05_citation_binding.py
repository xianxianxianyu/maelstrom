"""P3-05: Citation Binding node tests."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from maelstrom.graph.synthesis_nodes.citation_binding import citation_binding


def _claim(cid, paper_id, confidence=0.8, evi_id=None):
    eid = evi_id or f"e-{cid}"
    return {"claim_id": cid, "paper_id": paper_id, "text": "some claim", "confidence": confidence, "evidence_refs": [eid]}


def _evidence(eid, source_id, source_span="abstract"):
    return {"evidence_id": eid, "source_id": source_id, "source_span": source_span, "snippet": "text"}


def _paper(pid):
    return {"paper_id": pid, "title": "Paper", "abstract": "Abstract text about methods"}


def _alignment_response(results):
    return json.dumps(results)


@pytest.mark.asyncio
async def test_binding_aligned():
    resp = _alignment_response([{"claim_id": "c1", "aligned": True, "source_span": "abstract, sentence 1", "alignment_score": 0.9}])
    with patch("maelstrom.graph.synthesis_nodes.citation_binding.call_llm", return_value=resp):
        state = {
            "claims": [_claim("c1", "p1", evi_id="e1")],
            "evidences": [_evidence("e1", "p1")],
            "filtered_papers": [_paper("p1")],
            "llm_config": {},
        }
        result = await citation_binding(state)
    assert result["evidences"][0]["source_span"] == "abstract, sentence 1"


@pytest.mark.asyncio
async def test_binding_unverified():
    resp = _alignment_response([{"claim_id": "c1", "aligned": False, "source_span": "unverified", "alignment_score": 0.1}])
    with patch("maelstrom.graph.synthesis_nodes.citation_binding.call_llm", return_value=resp):
        state = {
            "claims": [_claim("c1", "p1", evi_id="e1")],
            "evidences": [_evidence("e1", "p1")],
            "filtered_papers": [_paper("p1")],
            "llm_config": {},
        }
        result = await citation_binding(state)
    assert result["evidences"][0]["source_span"] == "unverified"


@pytest.mark.asyncio
async def test_binding_confidence_reduction():
    resp = _alignment_response([{"claim_id": "c1", "aligned": False, "source_span": "unverified", "alignment_score": 0.1}])
    with patch("maelstrom.graph.synthesis_nodes.citation_binding.call_llm", return_value=resp):
        state = {
            "claims": [_claim("c1", "p1", confidence=0.8, evi_id="e1")],
            "evidences": [_evidence("e1", "p1")],
            "filtered_papers": [_paper("p1")],
            "llm_config": {},
        }
        result = await citation_binding(state)
    assert result["claims"][0]["confidence"] == pytest.approx(0.8 * 0.6, abs=0.01)


@pytest.mark.asyncio
async def test_binding_groups_by_paper():
    resp_p1 = _alignment_response([
        {"claim_id": "c1", "aligned": True, "source_span": "s1", "alignment_score": 0.9},
        {"claim_id": "c2", "aligned": True, "source_span": "s2", "alignment_score": 0.8},
    ])
    resp_p2 = _alignment_response([
        {"claim_id": "c3", "aligned": False, "source_span": "unverified", "alignment_score": 0.1},
    ])
    call_idx = 0

    async def mock_llm(prompt, *a, **kw):
        nonlocal call_idx
        call_idx += 1
        if "c1" in prompt or "c2" in prompt:
            return resp_p1
        return resp_p2

    with patch("maelstrom.graph.synthesis_nodes.citation_binding.call_llm", side_effect=mock_llm):
        state = {
            "claims": [_claim("c1", "p1", evi_id="e1"), _claim("c2", "p1", evi_id="e2"), _claim("c3", "p2", evi_id="e3")],
            "evidences": [_evidence("e1", "p1"), _evidence("e2", "p1"), _evidence("e3", "p2")],
            "filtered_papers": [_paper("p1"), _paper("p2")],
            "llm_config": {},
        }
        result = await citation_binding(state)
    assert call_idx == 2  # two groups
    assert result["evidences"][2]["source_span"] == "unverified"


@pytest.mark.asyncio
async def test_binding_llm_failure_preserves():
    with patch("maelstrom.graph.synthesis_nodes.citation_binding.call_llm", side_effect=Exception("fail")):
        state = {
            "claims": [_claim("c1", "p1", confidence=0.8, evi_id="e1")],
            "evidences": [_evidence("e1", "p1", source_span="abstract")],
            "filtered_papers": [_paper("p1")],
            "llm_config": {},
        }
        result = await citation_binding(state)
    assert result["claims"][0]["confidence"] == 0.8
    assert result["evidences"][0]["source_span"] == "abstract"


@pytest.mark.asyncio
async def test_binding_empty_claims():
    state = {"claims": [], "evidences": [], "filtered_papers": [], "llm_config": {}}
    result = await citation_binding(state)
    assert result["claims"] == []
