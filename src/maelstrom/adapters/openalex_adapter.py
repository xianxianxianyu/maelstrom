"""OpenAlex paper search adapter."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from maelstrom.adapters.base import BaseAdapter, RawPaperResult
from maelstrom.schemas.paper import Author, ExternalIds, PaperRecord

_OPENALEX_URL = "https://api.openalex.org/works"
_REQUEST_TIMEOUT = 10.0


class OpenAlexAdapter(BaseAdapter):
    """Adapter for the OpenAlex REST API."""

    def __init__(self, mailto: str | None = None) -> None:
        self._mailto = mailto

    @property
    def source_name(self) -> str:
        return "openalex"

    async def search(self, query: str, max_results: int = 20) -> list[RawPaperResult]:
        params: dict[str, str | int] = {
            "search": query,
            "per_page": min(max_results, 200),
        }
        if self._mailto:
            params["mailto"] = self._mailto

        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            resp = await client.get(_OPENALEX_URL, params=params)
            resp.raise_for_status()

        data = resp.json()
        results: list[RawPaperResult] = []
        for work in data.get("results", []):
            ids = work.get("ids") or {}
            openalex_id = ids.get("openalex", "")
            raw_doi = work.get("doi") or ""
            doi = _strip_doi_prefix(raw_doi)

            authors = []
            affiliations: list[str | None] = []
            for authorship in work.get("authorships") or []:
                author_obj = authorship.get("author") or {}
                name = author_obj.get("display_name", "")
                if name:
                    authors.append(name)
                insts = authorship.get("institutions") or []
                aff = insts[0].get("display_name") if insts else None
                affiliations.append(aff)

            venue = None
            loc = work.get("primary_location") or {}
            source = loc.get("source") or {}
            venue = source.get("display_name")

            abstract = _restore_abstract(work.get("abstract_inverted_index"))

            pdf_url = None
            oa = loc.get("pdf_url")
            if oa:
                pdf_url = oa

            results.append(RawPaperResult(
                source="openalex",
                raw_id=openalex_id,
                title=work.get("title") or "",
                authors=authors,
                abstract=abstract,
                year=work.get("publication_year"),
                venue=venue,
                doi=doi or None,
                pdf_url=pdf_url,
                citation_count=work.get("cited_by_count"),
                external_ids={"openalex_id": openalex_id, "doi": doi or None},
                extra={"affiliations": affiliations},
            ))
        return results
    def normalize(self, raw: RawPaperResult) -> PaperRecord:
        affiliations = raw.extra.get("affiliations", [])
        authors = []
        for i, name in enumerate(raw.authors):
            aff = affiliations[i] if i < len(affiliations) else None
            authors.append(Author(name=name, affiliation=aff))

        ext = raw.external_ids
        return PaperRecord(
            paper_id=f"openalex:{raw.raw_id}",
            title=raw.title,
            authors=authors,
            abstract=raw.abstract,
            year=raw.year,
            venue=raw.venue,
            doi=raw.doi,
            external_ids=ExternalIds(
                openalex_id=ext.get("openalex_id"),
                doi=ext.get("doi"),
            ),
            pdf_url=raw.pdf_url,
            source=self.source_name,
            citation_count=raw.citation_count,
            retrieved_at=datetime.now(timezone.utc),
        )


def _restore_abstract(inverted_index: dict | None) -> str:
    """Restore abstract text from OpenAlex abstract_inverted_index."""
    if not inverted_index:
        return ""
    word_positions: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort(key=lambda x: x[0])
    return " ".join(w for _, w in word_positions)


def _strip_doi_prefix(doi: str) -> str:
    """Remove https://doi.org/ prefix from DOI."""
    if doi.startswith("https://doi.org/"):
        return doi[len("https://doi.org/"):]
    return doi
