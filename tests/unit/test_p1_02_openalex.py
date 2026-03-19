"""P1-02: OpenAlexAdapter tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from maelstrom.adapters.openalex_adapter import OpenAlexAdapter, _restore_abstract, _strip_doi_prefix

SAMPLE_OA_RESPONSE = {
    "results": [
        {
            "id": "https://openalex.org/W123",
            "ids": {"openalex": "https://openalex.org/W123"},
            "title": "Transformers Survey",
            "abstract_inverted_index": {"We": [0], "survey": [1], "transformers": [2], "in": [3], "NLP.": [4]},
            "authorships": [
                {
                    "author": {"display_name": "Alice"},
                    "institutions": [{"display_name": "MIT"}],
                },
                {
                    "author": {"display_name": "Bob"},
                    "institutions": [],
                },
            ],
            "publication_year": 2023,
            "doi": "https://doi.org/10.1234/test",
            "primary_location": {
                "source": {"display_name": "Nature"},
                "pdf_url": "https://example.com/paper.pdf",
            },
            "cited_by_count": 500,
        },
    ],
}


def _mock_client(response_json):
    mock_resp = MagicMock()
    mock_resp.json.return_value = response_json
    mock_resp.raise_for_status = MagicMock()
    instance = AsyncMock()
    instance.get = AsyncMock(return_value=mock_resp)
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=False)
    return instance
@pytest.mark.asyncio
async def test_openalex_search_mock():
    adapter = OpenAlexAdapter()
    with patch("maelstrom.adapters.openalex_adapter.httpx.AsyncClient") as MC:
        MC.return_value = _mock_client(SAMPLE_OA_RESPONSE)
        results = await adapter.search("transformers")
    assert len(results) == 1
    assert results[0].title == "Transformers Survey"


@pytest.mark.asyncio
async def test_openalex_normalize():
    adapter = OpenAlexAdapter()
    with patch("maelstrom.adapters.openalex_adapter.httpx.AsyncClient") as MC:
        MC.return_value = _mock_client(SAMPLE_OA_RESPONSE)
        results = await adapter.search("transformers")
    paper = adapter.normalize(results[0])
    assert paper.paper_id.startswith("openalex:")
    assert paper.source == "openalex"
    assert paper.year == 2023
    assert paper.venue == "Nature"
    assert len(paper.authors) == 2
    assert paper.authors[0].name == "Alice"
    assert paper.authors[0].affiliation == "MIT"
    assert paper.authors[1].affiliation is None
    assert paper.citation_count == 500


def test_openalex_abstract_restore():
    idx = {"The": [0], "cat": [1], "sat": [2], "on": [3], "the": [4], "mat.": [5]}
    assert _restore_abstract(idx) == "The cat sat on the mat."


@pytest.mark.asyncio
async def test_openalex_doi_extraction():
    adapter = OpenAlexAdapter()
    with patch("maelstrom.adapters.openalex_adapter.httpx.AsyncClient") as MC:
        MC.return_value = _mock_client(SAMPLE_OA_RESPONSE)
        results = await adapter.search("test")
    paper = adapter.normalize(results[0])
    assert paper.doi == "10.1234/test"
    assert paper.external_ids.doi == "10.1234/test"


@pytest.mark.asyncio
async def test_openalex_mailto():
    adapter = OpenAlexAdapter(mailto="user@example.com")
    with patch("maelstrom.adapters.openalex_adapter.httpx.AsyncClient") as MC:
        client_instance = _mock_client(SAMPLE_OA_RESPONSE)
        MC.return_value = client_instance
        await adapter.search("test")
    call_kwargs = client_instance.get.call_args
    assert call_kwargs.kwargs["params"]["mailto"] == "user@example.com"


@pytest.mark.asyncio
async def test_openalex_timeout():
    adapter = OpenAlexAdapter()
    with patch("maelstrom.adapters.openalex_adapter.httpx.AsyncClient") as MC:
        instance = AsyncMock()
        instance.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MC.return_value = instance
        with pytest.raises(httpx.TimeoutException):
            await adapter.search("test")


def test_openalex_empty_abstract():
    assert _restore_abstract(None) == ""
    assert _restore_abstract({}) == ""
