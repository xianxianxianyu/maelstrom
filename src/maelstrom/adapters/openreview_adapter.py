"""OpenReview API v2 paper search adapter."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from maelstrom.adapters.base import BaseAdapter, RawPaperResult
from maelstrom.schemas.paper import Author, ExternalIds, PaperRecord

_OPENREVIEW_URL = "https://api2.openreview.net/notes/search"
_OPENREVIEW_BASE = "https://openreview.net"
_REQUEST_TIMEOUT = 10.0


class OpenReviewAdapter(BaseAdapter):
    """Adapter for the OpenReview API v2."""

    @property
    def source_name(self) -> str:
        return "openreview"

    async def search(self, query: str, max_results: int = 20) -> list[RawPaperResult]:
        params = {
            "query": query,
            "limit": min(max_results, 50),
            "offset": 0,
        }
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            resp = await client.get(_OPENREVIEW_URL, params=params)
            resp.raise_for_status()

        data = resp.json()
        results: list[RawPaperResult] = []
        for note in data.get("notes", []):
            content = note.get("content") or {}
            note_id = note.get("id", "")

            title = _val(content.get("title"))
            abstract = _val(content.get("abstract"))
            authors = _val(content.get("authors"))
            if isinstance(authors, str):
                authors = [authors]
            elif not isinstance(authors, list):
                authors = []
            venue = _val(content.get("venue"))

            pdf_path = _val(content.get("pdf"))
            pdf_url = None
            if pdf_path and pdf_path.startswith("/"):
                pdf_url = f"{_OPENREVIEW_BASE}{pdf_path}"
            elif pdf_path:
                pdf_url = pdf_path

            # Extract year from venue or cdate
            year = None
            if venue:
                import re
                m = re.search(r"20\d{2}", venue)
                if m:
                    year = int(m.group())
            if year is None:
                cdate = note.get("cdate")
                if cdate:
                    try:
                        year = datetime.fromtimestamp(cdate / 1000, tz=timezone.utc).year
                    except (ValueError, TypeError, OSError):
                        pass

            results.append(RawPaperResult(
                source="openreview",
                raw_id=note_id,
                title=title or "",
                authors=authors,
                abstract=abstract or "",
                year=year,
                venue=venue,
                pdf_url=pdf_url,
                external_ids={"openreview_id": note_id},
            ))
        return results

    def normalize(self, raw: RawPaperResult) -> PaperRecord:
        authors = [Author(name=a) for a in raw.authors]
        return PaperRecord(
            paper_id=f"openreview:{raw.raw_id}",
            title=raw.title,
            authors=authors,
            abstract=raw.abstract,
            year=raw.year,
            venue=raw.venue,
            doi=raw.doi,
            external_ids=ExternalIds(openreview_id=raw.raw_id),
            pdf_url=raw.pdf_url,
            source=self.source_name,
            citation_count=raw.citation_count,
            retrieved_at=datetime.now(timezone.utc),
        )


def _val(field: dict | str | list | None) -> str | list | None:
    """Extract .value from OpenReview content fields (may be dict with 'value' key or plain)."""
    if isinstance(field, dict):
        return field.get("value")
    return field
