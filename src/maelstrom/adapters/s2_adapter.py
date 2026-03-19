"""Semantic Scholar paper search adapter."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from maelstrom.adapters.base import BaseAdapter, RawPaperResult
from maelstrom.schemas.paper import Author, ExternalIds, PaperRecord

_S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_S2_FIELDS = "title,abstract,authors,year,venue,externalIds,citationCount,openAccessPdf"
_REQUEST_TIMEOUT = 10.0


class SemanticScholarAdapter(BaseAdapter):
    """Adapter for the Semantic Scholar Academic Graph API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    @property
    def source_name(self) -> str:
        return "s2"

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._api_key:
            headers["x-api-key"] = self._api_key
        return headers

    async def search(self, query: str, max_results: int = 20) -> list[RawPaperResult]:
        params = {
            "query": query,
            "limit": min(max_results, 100),
            "fields": _S2_FIELDS,
        }
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            resp = await client.get(
                _S2_SEARCH_URL, params=params, headers=self._headers()
            )
            resp.raise_for_status()

        data = resp.json()
        results: list[RawPaperResult] = []
        for paper in data.get("data", []):
            ext = paper.get("externalIds") or {}
            pdf_obj = paper.get("openAccessPdf") or {}
            authors = [a.get("name", "") for a in (paper.get("authors") or [])]

            results.append(RawPaperResult(
                source="s2",
                raw_id=paper.get("paperId", ""),
                title=paper.get("title", ""),
                authors=authors,
                abstract=paper.get("abstract") or "",
                year=paper.get("year"),
                venue=paper.get("venue") or None,
                doi=ext.get("DOI"),
                pdf_url=pdf_obj.get("url"),
                citation_count=paper.get("citationCount"),
                external_ids={
                    "s2_id": paper.get("paperId"),
                    "doi": ext.get("DOI"),
                    "arxiv_id": ext.get("ArXiv"),
                    "corpus_id": str(ext["CorpusId"]) if ext.get("CorpusId") is not None else None,
                },
            ))
        return results

    def normalize(self, raw: RawPaperResult) -> PaperRecord:
        authors = [Author(name=a) for a in raw.authors]
        ext = raw.external_ids
        return PaperRecord(
            paper_id=f"s2:{raw.raw_id}",
            title=raw.title,
            authors=authors,
            abstract=raw.abstract,
            year=raw.year,
            venue=raw.venue,
            doi=raw.doi,
            external_ids=ExternalIds(
                s2_id=ext.get("s2_id"),
                doi=ext.get("doi"),
                arxiv_id=ext.get("arxiv_id"),
                corpus_id=ext.get("corpus_id"),
            ),
            pdf_url=raw.pdf_url,
            source=self.source_name,
            citation_count=raw.citation_count,
            retrieved_at=datetime.now(timezone.utc),
        )
