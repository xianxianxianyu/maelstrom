"""P1-01: SemanticScholarAdapter tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from maelstrom.adapters.s2_adapter import SemanticScholarAdapter

SAMPLE_S2_RESPONSE = {
    "total": 2,
    "data": [
        {
            "paperId": "abc123",
            "title": "Attention Is All You Need",
            "abstract": "We propose a new architecture.",
            "authors": [
                {"authorId": "1", "name": "Ashish Vaswani"},
                {"authorId": "2", "name": "Noam Shazeer"},
            ],
            "year": 2017,
            "venue": "NeurIPS",
            "externalIds": {
                "DOI": "10.5555/3295222.3295349",
                "ArXiv": "1706.03762",
                "CorpusId": 215416146,
            },
            "citationCount": 90000,
            "openAccessPdf": {"url": "https://arxiv.org/pdf/1706.03762.pdf"},
        },
        {
            "paperId": "def456",
            "title": "BERT",
            "abstract": "Language model.",
            "authors": [{"authorId": "3", "name": "Jacob Devlin"}],
            "year": 2019,
            "venue": "NAACL",
            "externalIds": {"DOI": None, "CorpusId": 52967399},
            "citationCount": 50000,
            "openAccessPdf": None,
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
async def test_s2_search_mock():
    adapter = SemanticScholarAdapter()
    with patch("maelstrom.adapters.s2_adapter.httpx.AsyncClient") as MockClient:
        MockClient.return_value = _mock_client(SAMPLE_S2_RESPONSE)
        results = await adapter.search("transformer")
    assert len(results) == 2
    assert results[0].raw_id == "abc123"
    assert results[0].title == "Attention Is All You Need"


@pytest.mark.asyncio
async def test_s2_normalize():
    adapter = SemanticScholarAdapter()
    with patch("maelstrom.adapters.s2_adapter.httpx.AsyncClient") as MockClient:
        MockClient.return_value = _mock_client(SAMPLE_S2_RESPONSE)
        results = await adapter.search("transformer")
    paper = adapter.normalize(results[0])
    assert paper.paper_id == "s2:abc123"
    assert paper.source == "s2"
    assert paper.year == 2017
    assert paper.venue == "NeurIPS"
    assert len(paper.authors) == 2
    assert paper.authors[0].name == "Ashish Vaswani"
    assert paper.citation_count == 90000


@pytest.mark.asyncio
async def test_s2_external_ids():
    adapter = SemanticScholarAdapter()
    with patch("maelstrom.adapters.s2_adapter.httpx.AsyncClient") as MockClient:
        MockClient.return_value = _mock_client(SAMPLE_S2_RESPONSE)
        results = await adapter.search("transformer")
    paper = adapter.normalize(results[0])
    assert paper.external_ids.s2_id == "abc123"
    assert paper.external_ids.doi == "10.5555/3295222.3295349"
    assert paper.external_ids.arxiv_id == "1706.03762"
    assert paper.external_ids.corpus_id == "215416146"


@pytest.mark.asyncio
async def test_s2_with_api_key():
    adapter = SemanticScholarAdapter(api_key="test-key-123")
    with patch("maelstrom.adapters.s2_adapter.httpx.AsyncClient") as MockClient:
        client_instance = _mock_client(SAMPLE_S2_RESPONSE)
        MockClient.return_value = client_instance
        await adapter.search("test")
    # Verify header was passed
    call_kwargs = client_instance.get.call_args
    assert call_kwargs.kwargs["headers"]["x-api-key"] == "test-key-123"


@pytest.mark.asyncio
async def test_s2_without_api_key():
    adapter = SemanticScholarAdapter()
    with patch("maelstrom.adapters.s2_adapter.httpx.AsyncClient") as MockClient:
        client_instance = _mock_client(SAMPLE_S2_RESPONSE)
        MockClient.return_value = client_instance
        await adapter.search("test")
    call_kwargs = client_instance.get.call_args
    assert "x-api-key" not in call_kwargs.kwargs.get("headers", {})


@pytest.mark.asyncio
async def test_s2_pdf_url():
    adapter = SemanticScholarAdapter()
    with patch("maelstrom.adapters.s2_adapter.httpx.AsyncClient") as MockClient:
        MockClient.return_value = _mock_client(SAMPLE_S2_RESPONSE)
        results = await adapter.search("test")
    paper0 = adapter.normalize(results[0])
    paper1 = adapter.normalize(results[1])
    assert paper0.pdf_url == "https://arxiv.org/pdf/1706.03762.pdf"
    assert paper1.pdf_url is None


@pytest.mark.asyncio
async def test_s2_timeout():
    adapter = SemanticScholarAdapter()
    with patch("maelstrom.adapters.s2_adapter.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance
        with pytest.raises(httpx.TimeoutException):
            await adapter.search("test")
