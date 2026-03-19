"""P1-04: PaperRetriever tests."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from maelstrom.adapters.base import BaseAdapter, RawPaperResult
from maelstrom.schemas.paper import Author, ExternalIds, PaperRecord
from maelstrom.services.paper_retriever import PaperRetriever


def _make_paper(source: str, pid: str, doi: str | None = None) -> PaperRecord:
    return PaperRecord(
        paper_id=f"{source}:{pid}",
        title=f"Paper {pid}",
        authors=[Author(name="Test")],
        abstract="Abstract",
        year=2024,
        source=source,
        doi=doi,
        external_ids=ExternalIds(doi=doi),
        retrieved_at=datetime.now(timezone.utc),
    )


def _make_raw(source: str, rid: str) -> RawPaperResult:
    return RawPaperResult(source=source, raw_id=rid, title=f"Paper {rid}")


def _make_adapter(name: str, papers: list[PaperRecord], delay: float = 0.0, error: Exception | None = None):
    adapter = MagicMock(spec=BaseAdapter)
    adapter.source_name = name

    async def _search(query, max_results=20):
        if delay:
            await asyncio.sleep(delay)
        if error:
            raise error
        return [_make_raw(name, p.paper_id) for p in papers]

    adapter.search = AsyncMock(side_effect=_search)
    adapter.normalize = MagicMock(side_effect=lambda raw: papers[0] if papers else None)
    # Make normalize return correct paper for each raw
    if papers:
        adapter.normalize = MagicMock(side_effect=lambda raw: next(
            (p for p in papers if raw.raw_id == p.paper_id), papers[0]
        ))
    return adapter
@pytest.mark.asyncio
async def test_parallel_search():
    """Four sources run in parallel — total time ≈ slowest, not sum."""
    adapters = [
        _make_adapter("a", [_make_paper("a", "1")], delay=0.1),
        _make_adapter("b", [_make_paper("b", "2")], delay=0.1),
        _make_adapter("c", [_make_paper("c", "3")], delay=0.1),
        _make_adapter("d", [_make_paper("d", "4")], delay=0.1),
    ]
    retriever = PaperRetriever(adapters)
    t0 = time.monotonic()
    result = await retriever.search_with_fallback("test")
    elapsed = time.monotonic() - t0
    assert len(result.papers) == 4
    # Parallel: should be ~0.1s, not ~0.4s
    assert elapsed < 0.3


@pytest.mark.asyncio
async def test_returns_all_sources_no_dedup():
    """Two sources return same DOI — PaperRetriever does NOT dedup."""
    p1 = _make_paper("arxiv", "1", doi="10.1234/test")
    p2 = _make_paper("s2", "2", doi="10.1234/test")
    adapters = [
        _make_adapter("arxiv", [p1]),
        _make_adapter("s2", [p2]),
    ]
    retriever = PaperRetriever(adapters)
    result = await retriever.search_with_fallback("test")
    assert len(result.papers) == 2  # Both kept, no dedup


@pytest.mark.asyncio
async def test_per_adapter_normalize():
    """Each result goes through adapter.normalize()."""
    p = _make_paper("arxiv", "1")
    adapter = _make_adapter("arxiv", [p])
    retriever = PaperRetriever([adapter])
    result = await retriever.search_with_fallback("test")
    assert len(result.papers) == 1
    adapter.normalize.assert_called_once()


@pytest.mark.asyncio
async def test_fallback_one_source_fails():
    """One source errors, others still return results."""
    adapters = [
        _make_adapter("a", [_make_paper("a", "1")]),
        _make_adapter("b", [], error=RuntimeError("API down")),
        _make_adapter("c", [_make_paper("c", "3")]),
    ]
    retriever = PaperRetriever(adapters)
    result = await retriever.search_with_fallback("test")
    assert len(result.papers) == 2
    assert result.is_degraded is True
    statuses = {s.source: s for s in result.source_statuses}
    assert statuses["a"].status == "ok"
    assert statuses["b"].status == "error"
    assert statuses["c"].status == "ok"


@pytest.mark.asyncio
async def test_fallback_degraded():
    """Only one source succeeds → is_degraded=True."""
    adapters = [
        _make_adapter("a", [_make_paper("a", "1")]),
        _make_adapter("b", [], error=RuntimeError("fail")),
        _make_adapter("c", [], error=RuntimeError("fail")),
    ]
    retriever = PaperRetriever(adapters)
    result = await retriever.search_with_fallback("test")
    assert len(result.papers) == 1
    assert result.is_degraded is True


@pytest.mark.asyncio
async def test_fallback_all_fail():
    """All sources fail → empty papers, all degraded."""
    adapters = [
        _make_adapter("a", [], error=RuntimeError("fail")),
        _make_adapter("b", [], error=RuntimeError("fail")),
    ]
    retriever = PaperRetriever(adapters)
    result = await retriever.search_with_fallback("test")
    assert len(result.papers) == 0
    assert result.is_degraded is True
    assert all(s.status == "error" for s in result.source_statuses)


@pytest.mark.asyncio
async def test_source_statuses():
    """Verify SourceStatus fields are populated correctly."""
    adapters = [
        _make_adapter("arxiv", [_make_paper("arxiv", "1"), _make_paper("arxiv", "2")]),
        _make_adapter("s2", [_make_paper("s2", "3")]),
    ]
    retriever = PaperRetriever(adapters)
    result = await retriever.search_with_fallback("test")
    statuses = {s.source: s for s in result.source_statuses}
    assert statuses["arxiv"].count == 2
    assert statuses["s2"].count == 1
    assert statuses["arxiv"].latency_ms >= 0
    assert statuses["arxiv"].status == "ok"
    assert statuses["arxiv"].error_msg is None


@pytest.mark.asyncio
async def test_per_source_timeout():
    """Source exceeding timeout gets status=timeout, doesn't block others."""
    import maelstrom.services.paper_retriever as mod
    original = mod._PER_SOURCE_TIMEOUT
    mod._PER_SOURCE_TIMEOUT = 0.05  # 50ms timeout for test

    adapters = [
        _make_adapter("fast", [_make_paper("fast", "1")], delay=0.0),
        _make_adapter("slow", [_make_paper("slow", "2")], delay=1.0),
    ]
    retriever = PaperRetriever(adapters)
    t0 = time.monotonic()
    result = await retriever.search_with_fallback("test")
    elapsed = time.monotonic() - t0

    mod._PER_SOURCE_TIMEOUT = original

    assert elapsed < 0.5  # Didn't wait for slow source
    assert len(result.papers) == 1
    statuses = {s.source: s for s in result.source_statuses}
    assert statuses["fast"].status == "ok"
    assert statuses["slow"].status == "timeout"


@pytest.mark.asyncio
async def test_rate_limited_source_is_skipped_for_rest_of_run():
    request = httpx.Request("GET", "https://api.semanticscholar.org/graph/v1/paper/search")
    response = httpx.Response(429, request=request)
    rate_limited = httpx.HTTPStatusError("429", request=request, response=response)

    adapters = [
        _make_adapter("arxiv", [_make_paper("arxiv", "1")]),
        _make_adapter("s2", [], error=rate_limited),
    ]
    retriever = PaperRetriever(adapters)

    first = await retriever.search_with_fallback("test-1")
    second = await retriever.search_with_fallback("test-2")

    first_statuses = {s.source: s for s in first.source_statuses}
    second_statuses = {s.source: s for s in second.source_statuses}

    assert first_statuses["s2"].status == "rate_limited"
    assert second_statuses["s2"].status == "rate_limited"
    assert adapters[1].search.await_count == 1
