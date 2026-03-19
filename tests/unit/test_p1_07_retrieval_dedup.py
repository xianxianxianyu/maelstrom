"""P1-07: paper_retrieval + normalize_dedup node tests."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from maelstrom.graph.gap_engine import GapEngineState
from maelstrom.graph.nodes.paper_retrieval import paper_retrieval
from maelstrom.graph.nodes.normalize_dedup import normalize_dedup
from maelstrom.schemas.paper import Author, ExternalIds, PaperRecord
from maelstrom.schemas.search import SearchResult, SourceStatus


def _paper(pid: str, source: str = "arxiv", doi: str | None = None,
           s2_id: str | None = None, corpus_id: str | None = None,
           title: str = "Paper", author: str = "Smith") -> dict:
    return PaperRecord(
        paper_id=pid, title=title, authors=[Author(name=author)],
        abstract="abs", year=2024, source=source, doi=doi,
        external_ids=ExternalIds(doi=doi, s2_id=s2_id, corpus_id=corpus_id),
        retrieved_at=datetime.now(timezone.utc),
    ).model_dump()


def _mock_retriever(results_per_query: list[list[PaperRecord]], statuses=None):
    retriever = MagicMock()
    call_count = 0

    async def _search(query, max_results=50):
        nonlocal call_count
        idx = min(call_count, len(results_per_query) - 1)
        papers = results_per_query[idx]
        call_count += 1
        sts = statuses or [SourceStatus(source="mock", status="ok", count=len(papers))]
        return SearchResult(papers=papers, source_statuses=sts, is_degraded=False)

    retriever.search_with_fallback = AsyncMock(side_effect=_search)
    return retriever


# --- paper_retrieval tests ---

@pytest.mark.asyncio
async def test_retrieval_calls_all_queries():
    p1 = PaperRecord(paper_id="1", title="A", source="arxiv", retrieved_at=datetime.now(timezone.utc))
    retriever = _mock_retriever([[p1], [p1]])
    state: GapEngineState = {"expanded_queries": ["q1", "q2"]}
    await paper_retrieval(state, retriever=retriever)
    assert retriever.search_with_fallback.call_count == 2
@pytest.mark.asyncio
async def test_retrieval_merges_results():
    p1 = PaperRecord(paper_id="1", title="A", source="arxiv", retrieved_at=datetime.now(timezone.utc))
    p2 = PaperRecord(paper_id="2", title="B", source="s2", retrieved_at=datetime.now(timezone.utc))
    retriever = _mock_retriever([[p1], [p2]])
    state: GapEngineState = {"expanded_queries": ["q1", "q2"]}
    await paper_retrieval(state, retriever=retriever)
    assert len(state["raw_papers"]) == 2


@pytest.mark.asyncio
async def test_retrieval_search_result():
    p1 = PaperRecord(paper_id="1", title="A", source="arxiv", retrieved_at=datetime.now(timezone.utc))
    retriever = _mock_retriever([[p1]])
    state: GapEngineState = {"expanded_queries": ["q1"]}
    await paper_retrieval(state, retriever=retriever)
    assert "source_statuses" in state["search_result"]


@pytest.mark.asyncio
async def test_retrieval_all_fail():
    sts = [SourceStatus(source="mock", status="error", count=0, error_msg="fail")]
    retriever = _mock_retriever([[]], statuses=sts)
    state: GapEngineState = {"expanded_queries": ["q1"]}
    await paper_retrieval(state, retriever=retriever)
    assert state.get("error") is not None


# --- normalize_dedup tests ---

def test_dedup_doi():
    papers = [
        _paper("1", source="arxiv", doi="10.1234/x"),
        _paper("2", source="s2", doi="10.1234/x"),
    ]
    state: GapEngineState = {"raw_papers": papers}
    normalize_dedup(state)
    assert len(state["papers"]) == 1


def test_dedup_s2_id():
    papers = [
        _paper("1", source="arxiv", s2_id="abc"),
        _paper("2", source="s2", s2_id="abc"),
    ]
    state: GapEngineState = {"raw_papers": papers}
    normalize_dedup(state)
    assert len(state["papers"]) == 1


def test_dedup_title_fuzzy():
    papers = [
        _paper("1", title="Attention Is All You Need", author="Vaswani"),
        _paper("2", title="Attention is All You Need", author="Vaswani"),
    ]
    state: GapEngineState = {"raw_papers": papers}
    normalize_dedup(state)
    assert len(state["papers"]) == 1


def test_dedup_no_false_positive():
    """Similar titles but different first authors → no dedup."""
    papers = [
        _paper("1", title="Attention Is All You Need", author="Vaswani"),
        _paper("2", title="Attention Is All You Need", author="Smith"),
    ]
    state: GapEngineState = {"raw_papers": papers}
    normalize_dedup(state)
    assert len(state["papers"]) == 2


def test_dedup_merge_external_ids():
    papers = [
        _paper("1", source="arxiv", doi="10.1234/x"),
        _paper("2", source="s2", doi="10.1234/x", s2_id="s2abc"),
    ]
    state: GapEngineState = {"raw_papers": papers}
    normalize_dedup(state)
    merged = state["papers"][0]
    ext = merged["external_ids"]
    assert ext.get("doi") == "10.1234/x"
    assert ext.get("s2_id") == "s2abc"


def test_dedup_keeps_richest():
    """Richer record (more fields) is kept as base."""
    sparse = _paper("1", source="arxiv", doi="10.1234/x", title="Paper")
    rich = _paper("2", source="s2", doi="10.1234/x", title="Paper")
    # Make rich actually richer by adding more fields
    rich["venue"] = "NeurIPS"
    rich["citation_count"] = 500
    rich["pdf_url"] = "https://example.com/paper.pdf"

    state: GapEngineState = {"raw_papers": [sparse, rich]}
    normalize_dedup(state)
    result = state["papers"][0]
    assert result["venue"] == "NeurIPS"
    assert result["citation_count"] == 500


def test_dedup_input_already_normalized():
    """normalize_dedup doesn't modify already-normalized fields."""
    paper = _paper("1", title="My Title", source="arxiv")
    state: GapEngineState = {"raw_papers": [paper]}
    normalize_dedup(state)
    assert state["papers"][0]["title"] == "My Title"
    assert state["papers"][0]["year"] == 2024
