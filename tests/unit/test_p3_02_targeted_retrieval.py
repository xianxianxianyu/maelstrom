"""P3-02: Targeted Retrieval node tests."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maelstrom.graph.synthesis_nodes.targeted_retrieval import targeted_retrieval, _generate_queries
from maelstrom.services.evidence_memory import EvidenceHit


def _make_hit(source_id, title="Paper", snippet="abstract text"):
    return EvidenceHit(evidence_id="e1", source_type="paper", source_id=source_id, title=title, snippet=snippet)


def _make_paper(paper_id, title="Paper"):
    m = MagicMock()
    m.paper_id = paper_id
    m.model_dump.return_value = {"paper_id": paper_id, "title": title, "abstract": "abs"}
    return m


@pytest.mark.asyncio
async def test_retrieval_from_evidence_memory():
    mem = AsyncMock()
    mem.search.return_value = [_make_hit("p1"), _make_hit("p2")]
    with patch("maelstrom.graph.synthesis_nodes.targeted_retrieval.get_evidence_memory", return_value=mem):
        with patch("maelstrom.graph.synthesis_nodes.targeted_retrieval.call_llm", return_value='["q1"]'):
            state = {"session_id": "s1", "topic": "NER", "llm_config": {}}
            result = await targeted_retrieval(state)
    assert len(result["targeted_papers"]) == 2
    assert result["targeted_papers"][0]["paper_id"] == "p1"


@pytest.mark.asyncio
async def test_retrieval_incremental():
    mem = AsyncMock()
    mem.search.return_value = [_make_hit("p1"), _make_hit("p2")]
    mem.ingest_text = AsyncMock()
    retriever = AsyncMock()
    retriever.search.return_value = [_make_paper("p3"), _make_paper("p4"), _make_paper("p5")]
    with patch("maelstrom.graph.synthesis_nodes.targeted_retrieval.get_evidence_memory", return_value=mem):
        with patch("maelstrom.graph.synthesis_nodes.targeted_retrieval.call_llm", return_value='["q1"]'):
            state = {"session_id": "s1", "topic": "NER", "llm_config": {}, "_retriever": retriever}
            result = await targeted_retrieval(state)
    # 2 from memory + 3 new
    assert len(result["targeted_papers"]) == 5


@pytest.mark.asyncio
async def test_retrieval_dedup():
    mem = AsyncMock()
    mem.search.return_value = [_make_hit("p1")]
    mem.ingest_text = AsyncMock()
    retriever = AsyncMock()
    retriever.search.return_value = [_make_paper("p1"), _make_paper("p2")]  # p1 is duplicate
    with patch("maelstrom.graph.synthesis_nodes.targeted_retrieval.get_evidence_memory", return_value=mem):
        with patch("maelstrom.graph.synthesis_nodes.targeted_retrieval.call_llm", return_value='["q1"]'):
            state = {"session_id": "s1", "topic": "NER", "llm_config": {}, "_retriever": retriever}
            result = await targeted_retrieval(state)
    assert len(result["targeted_papers"]) == 2  # p1 + p2, no dup
    ids = [p["paper_id"] for p in result["targeted_papers"]]
    assert ids.count("p1") == 1


@pytest.mark.asyncio
async def test_retrieval_new_papers_ingested():
    mem = AsyncMock()
    mem.search.return_value = []
    mem.ingest_text = AsyncMock()
    retriever = AsyncMock()
    retriever.search.return_value = [_make_paper("p1")]
    with patch("maelstrom.graph.synthesis_nodes.targeted_retrieval.get_evidence_memory", return_value=mem):
        with patch("maelstrom.graph.synthesis_nodes.targeted_retrieval.call_llm", return_value='["q1"]'):
            state = {"session_id": "s1", "topic": "NER", "llm_config": {}, "_retriever": retriever}
            await targeted_retrieval(state)
    mem.ingest_text.assert_called_once()


@pytest.mark.asyncio
async def test_retrieval_no_papers_error():
    mem = AsyncMock()
    mem.search.return_value = []
    with patch("maelstrom.graph.synthesis_nodes.targeted_retrieval.get_evidence_memory", return_value=mem):
        with patch("maelstrom.graph.synthesis_nodes.targeted_retrieval.call_llm", return_value='["q1"]'):
            state = {"session_id": "s1", "topic": "NER", "llm_config": {}}
            result = await targeted_retrieval(state)
    assert result["targeted_papers"] == []


@pytest.mark.asyncio
async def test_targeted_query_generation():
    with patch("maelstrom.graph.synthesis_nodes.targeted_retrieval.call_llm", return_value='["BERT NER", "CRF sequence"]'):
        queries = await _generate_queries("NER", None, {})
    assert "NER" in queries  # original always included
    assert "BERT NER" in queries
    assert len(queries) == 3


@pytest.mark.asyncio
async def test_retrieval_gap_input():
    mem = AsyncMock()
    mem.search.return_value = []
    with patch("maelstrom.graph.synthesis_nodes.targeted_retrieval.get_evidence_memory", return_value=mem):
        with patch("maelstrom.graph.synthesis_nodes.targeted_retrieval.call_llm", return_value='["gap query"]') as mock_llm:
            state = {
                "session_id": "s1", "topic": "NER", "llm_config": {},
                "gap_info": {"title": "Low-resource NER", "summary": "Few datasets"},
            }
            await targeted_retrieval(state)
    # LLM prompt should contain gap info
    call_args = mock_llm.call_args[0][0]
    assert "Low-resource NER" in call_args


@pytest.mark.asyncio
async def test_retrieval_topic_input():
    mem = AsyncMock()
    mem.search.return_value = []
    with patch("maelstrom.graph.synthesis_nodes.targeted_retrieval.get_evidence_memory", return_value=mem):
        with patch("maelstrom.graph.synthesis_nodes.targeted_retrieval.call_llm", return_value='["topic query"]') as mock_llm:
            state = {"session_id": "s1", "topic": "Transformer for NER", "llm_config": {}}
            await targeted_retrieval(state)
    call_args = mock_llm.call_args[0][0]
    assert "Transformer for NER" in call_args
