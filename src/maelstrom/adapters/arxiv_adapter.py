"""arXiv paper search adapter."""
from __future__ import annotations

import asyncio
import html
import re
import unicodedata
from datetime import datetime, timezone

import httpx

from maelstrom.adapters.base import BaseAdapter, RawPaperResult
from maelstrom.schemas.paper import Author, ExternalIds, PaperRecord

_ARXIV_API = "https://export.arxiv.org/api/query"
_REQUEST_TIMEOUT = 10.0
_RATE_LIMIT_INTERVAL = 1.0 / 3  # 3 req/s


class ArxivAdapter(BaseAdapter):
    """Adapter for the arXiv search API."""

    def __init__(self) -> None:
        self._last_request_time: float = 0.0

    @property
    def source_name(self) -> str:
        return "arxiv"

    async def _rate_limit(self) -> None:
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < _RATE_LIMIT_INTERVAL:
            await asyncio.sleep(_RATE_LIMIT_INTERVAL - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    async def search(self, query: str, max_results: int = 20) -> list[RawPaperResult]:
        await self._rate_limit()
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
        }
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            resp = await client.get(_ARXIV_API, params=params)
            resp.raise_for_status()
        return self._parse_atom(resp.text)
    def _parse_atom(self, xml_text: str) -> list[RawPaperResult]:
        """Parse Atom XML from arXiv API into RawPaperResult list."""
        import xml.etree.ElementTree as ET

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(xml_text)
        results: list[RawPaperResult] = []

        for entry in root.findall("atom:entry", ns):
            arxiv_id_url = entry.findtext("atom:id", "", ns)
            arxiv_id = arxiv_id_url.rsplit("/abs/", 1)[-1] if "/abs/" in arxiv_id_url else arxiv_id_url
            # Strip version suffix for canonical id
            arxiv_id_clean = re.sub(r"v\d+$", "", arxiv_id)

            title = entry.findtext("atom:title", "", ns)
            abstract = entry.findtext("atom:summary", "", ns)
            published = entry.findtext("atom:published", "", ns)

            authors = []
            for author_el in entry.findall("atom:author", ns):
                name = author_el.findtext("atom:name", "", ns)
                if name:
                    authors.append(name)

            # Extract DOI from arxiv:doi if present
            doi_el = entry.find("{http://arxiv.org/schemas/atom}doi")
            doi = doi_el.text.strip() if doi_el is not None and doi_el.text else None

            # PDF link
            pdf_url = None
            for link in entry.findall("atom:link", ns):
                if link.get("title") == "pdf":
                    pdf_url = link.get("href")
                    break

            year = None
            if published:
                try:
                    year = int(published[:4])
                except ValueError:
                    pass

            results.append(RawPaperResult(
                source="arxiv",
                raw_id=arxiv_id_clean,
                title=title,
                authors=authors,
                abstract=abstract,
                year=year,
                doi=doi,
                pdf_url=pdf_url,
                published_date=published,
                external_ids={"arxiv_id": arxiv_id_clean},
            ))

        return results

    def normalize(self, raw: RawPaperResult) -> PaperRecord:
        title = _clean_text(raw.title)
        abstract = _clean_text(raw.abstract)
        authors = [Author(name=_clean_text(a)) for a in raw.authors]

        published_iso = None
        if raw.published_date:
            published_iso = raw.published_date

        return PaperRecord(
            paper_id=f"arxiv:{raw.raw_id}",
            title=title,
            authors=authors,
            abstract=abstract,
            year=raw.year,
            venue=None,
            doi=raw.doi,
            external_ids=ExternalIds(arxiv_id=raw.raw_id),
            pdf_url=raw.pdf_url,
            source=self.source_name,
            citation_count=raw.citation_count,
            retrieved_at=datetime.now(timezone.utc),
        )


def _clean_text(text: str) -> str:
    """Strip HTML tags, collapse whitespace, NFC normalize."""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return unicodedata.normalize("NFC", text)
