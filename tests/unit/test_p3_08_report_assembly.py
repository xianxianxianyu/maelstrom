"""P3-08: Report Assembly node tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from maelstrom.graph.synthesis_nodes.report_assembly import report_assembly, _DEFAULT_SUMMARY


def _base_state(**kw):
    defaults = {
        "session_id": "s1", "run_id": "r1", "topic": "NER", "llm_config": {},
        "filtered_papers": [{"paper_id": "p1"}, {"paper_id": "p2"}],
        "claims": [{"claim_id": "c1", "text": "BERT works", "claim_type": "method_effectiveness"}],
        "evidences": [{"evidence_id": "e1", "source_id": "p1"}],
        "consensus_points": [{"statement": "consensus"}],
        "conflict_points": [{"statement": "conflict"}],
        "open_questions": ["What about X?"],
        "feasibility_memo": {"verdict": "advance", "memo_id": "m1"},
    }
    defaults.update(kw)
    return defaults


@pytest.mark.asyncio
async def test_assembly_complete_report():
    mem = AsyncMock()
    with patch("maelstrom.graph.synthesis_nodes.report_assembly.call_llm", return_value="Summary text"):
        with patch("maelstrom.graph.synthesis_nodes.report_assembly.get_evidence_memory", return_value=mem):
            result = await report_assembly(_base_state())
    report = result["review_report"]
    assert report["topic"] == "NER"
    assert len(report["claims"]) == 1
    assert len(report["consensus_points"]) == 1
    assert len(report["conflict_points"]) == 1
    assert report["open_questions"] == ["What about X?"]
    assert report["paper_count"] == 2
    assert report["report_id"]


@pytest.mark.asyncio
async def test_assembly_includes_feasibility():
    mem = AsyncMock()
    with patch("maelstrom.graph.synthesis_nodes.report_assembly.call_llm", return_value="Summary"):
        with patch("maelstrom.graph.synthesis_nodes.report_assembly.get_evidence_memory", return_value=mem):
            result = await report_assembly(_base_state())
    assert result["feasibility_memo"]["verdict"] == "advance"
    assert result["review_report"] is not None


@pytest.mark.asyncio
async def test_assembly_executive_summary():
    mem = AsyncMock()
    with patch("maelstrom.graph.synthesis_nodes.report_assembly.call_llm", return_value="Generated summary"):
        with patch("maelstrom.graph.synthesis_nodes.report_assembly.get_evidence_memory", return_value=mem):
            result = await report_assembly(_base_state())
    assert result["review_report"]["executive_summary"] == "Generated summary"


@pytest.mark.asyncio
async def test_assembly_summary_fallback():
    mem = AsyncMock()
    with patch("maelstrom.graph.synthesis_nodes.report_assembly.call_llm", side_effect=Exception("fail")):
        with patch("maelstrom.graph.synthesis_nodes.report_assembly.get_evidence_memory", return_value=mem):
            result = await report_assembly(_base_state())
    assert result["review_report"]["executive_summary"] == _DEFAULT_SUMMARY


@pytest.mark.asyncio
async def test_assembly_evidence_memory():
    mem = AsyncMock()
    with patch("maelstrom.graph.synthesis_nodes.report_assembly.call_llm", return_value="Summary"):
        with patch("maelstrom.graph.synthesis_nodes.report_assembly.get_evidence_memory", return_value=mem):
            await report_assembly(_base_state())
    # review + 1 claim = 2 ingest calls
    assert mem.ingest_text.call_count == 2
    first_call = mem.ingest_text.call_args_list[0]
    assert first_call[0][1] == "review"  # source_type


@pytest.mark.asyncio
async def test_assembly_empty_claims():
    mem = AsyncMock()
    with patch("maelstrom.graph.synthesis_nodes.report_assembly.call_llm", return_value="Summary"):
        with patch("maelstrom.graph.synthesis_nodes.report_assembly.get_evidence_memory", return_value=mem):
            result = await report_assembly(_base_state(claims=[], evidences=[]))
    assert result["review_report"]["claims"] == []
    assert result["review_report"]["report_id"]
