"""Unified paper retriever — parallel search across adapters."""
from __future__ import annotations

import asyncio
import httpx
import logging
import time
from typing import Any

from maelstrom.adapters.base import BaseAdapter
from maelstrom.schemas.paper import PaperRecord
from maelstrom.schemas.search import SearchResult, SourceStatus

logger = logging.getLogger(__name__)

_PER_SOURCE_TIMEOUT = 10.0


class PaperRetriever:
    """Parallel paper search across multiple adapters with fallback."""

    def __init__(self, adapters: list[BaseAdapter]) -> None:
        self._adapters = adapters
        self._rate_limited_sources: set[str] = set()

    async def search(self, query: str, max_results: int = 50) -> list[PaperRecord]:
        """Simple search returning merged papers (may contain cross-source duplicates)."""
        result = await self.search_with_fallback(query, max_results)
        return result.papers

    async def search_with_fallback(
        self, query: str, max_results: int = 50
    ) -> SearchResult:
        """Search all adapters in parallel with per-source timeout and fallback."""
        active_adapters = [
            adapter for adapter in self._adapters
            if adapter.source_name not in self._rate_limited_sources
        ]
        per_source = max(max_results // len(active_adapters), 10) if active_adapters else 0

        skipped_statuses = [
            SourceStatus(
                source=adapter.source_name,
                status="rate_limited",
                count=0,
                latency_ms=0,
                error_msg="Skipped after earlier HTTP 429 in this run",
            )
            for adapter in self._adapters
            if adapter.source_name in self._rate_limited_sources
        ]

        tasks = [
            self._search_one(adapter, query, per_source)
            for adapter in active_adapters
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False) if tasks else []

        all_papers: list[PaperRecord] = []
        statuses: list[SourceStatus] = skipped_statuses
        ok_count = 0

        for papers, status in results:
            statuses.append(status)
            if status.status == "ok":
                all_papers.extend(papers)
                ok_count += 1
        is_degraded = ok_count < len(self._adapters)

        return SearchResult(
            papers=all_papers,
            source_statuses=statuses,
            is_degraded=is_degraded,
        )

    async def _search_one(
        self, adapter: BaseAdapter, query: str, max_results: int
    ) -> tuple[list[PaperRecord], SourceStatus]:
        """Search a single adapter with timeout, returning papers + status."""
        source = adapter.source_name
        t0 = time.monotonic()
        try:
            raw_results = await asyncio.wait_for(
                adapter.search(query, max_results),
                timeout=_PER_SOURCE_TIMEOUT,
            )
            papers = [adapter.normalize(r) for r in raw_results]
            latency = int((time.monotonic() - t0) * 1000)
            return papers, SourceStatus(
                source=source, status="ok", count=len(papers), latency_ms=latency,
            )
        except asyncio.TimeoutError:
            latency = int((time.monotonic() - t0) * 1000)
            logger.warning("Adapter %s timed out after %dms", source, latency)
            return [], SourceStatus(
                source=source, status="timeout", count=0,
                latency_ms=latency, error_msg="Request timed out",
            )
        except Exception as e:
            latency = int((time.monotonic() - t0) * 1000)
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429:
                self._rate_limited_sources.add(source)
                logger.warning(
                    "Adapter %s hit HTTP 429 after %dms; disabling it for the remainder of this run",
                    source,
                    latency,
                )
                return [], SourceStatus(
                    source=source,
                    status="rate_limited",
                    count=0,
                    latency_ms=latency,
                    error_msg="HTTP 429 rate limited",
                )
            logger.warning("Adapter %s failed: %s", source, e)
            return [], SourceStatus(
                source=source, status="error", count=0,
                latency_ms=latency, error_msg=str(e),
            )
