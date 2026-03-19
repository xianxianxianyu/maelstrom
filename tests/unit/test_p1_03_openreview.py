"""P1-03: OpenReviewAdapter tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from maelstrom.adapters.openreview_adapter import OpenReviewAdapter

SAMPLE_OR_RESPONSE = {
    "notes": [
        {
            "id": "abc123note",
            "content": {
                "title": {"value": "ViT for Everything"},
                "abstract": {"value": "We apply ViT broadly."},
                "authors": {"value": ["Alice", "Bob"]},
                "venue": {"value": "ICLR 2024"},
                "pdf": {"value": "/pdf/abc123note.pdf"},
            },
            "cdate": 1704067200000,  # 2024-01-01
        },
        {
            "id": "def456note",
            "content": {
                "title": {"value": "Second Paper"},
                "abstract": {"value": "Abstract two."},
                "authors": {"value": ["Carol"]},
                "venue": {"value": "NeurIPS 2023"},
                "pdf": {"value": "https://example.com/paper.pdf"},
            },
        },
    ],
}


def _mock_client(response_json, status_code=200):
    mock_resp = MagicMock()
    mock_resp.json.return_value = response_json
    mock_resp.status_code = status_code
    if status_code >= 400:
        mock_resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("error", request=MagicMock(), response=mock_resp)
        )
    else:
        mock_resp.raise_for_status = MagicMock()
    instance = AsyncMock()
    instance.get = AsyncMock(return_value=mock_resp)
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=False)
    return instance
@pytest.mark.asyncio
async def test_openreview_search_mock():
    adapter = OpenReviewAdapter()
    with patch("maelstrom.adapters.openreview_adapter.httpx.AsyncClient") as MC:
        MC.return_value = _mock_client(SAMPLE_OR_RESPONSE)
        results = await adapter.search("vision transformer")
    assert len(results) == 2
    assert results[0].raw_id == "abc123note"
    assert results[0].title == "ViT for Everything"


@pytest.mark.asyncio
async def test_openreview_normalize():
    adapter = OpenReviewAdapter()
    with patch("maelstrom.adapters.openreview_adapter.httpx.AsyncClient") as MC:
        MC.return_value = _mock_client(SAMPLE_OR_RESPONSE)
        results = await adapter.search("test")
    paper = adapter.normalize(results[0])
    assert paper.paper_id == "openreview:abc123note"
    assert paper.source == "openreview"
    assert len(paper.authors) == 2
    assert paper.authors[0].name == "Alice"
    assert paper.abstract == "We apply ViT broadly."


@pytest.mark.asyncio
async def test_openreview_venue():
    adapter = OpenReviewAdapter()
    with patch("maelstrom.adapters.openreview_adapter.httpx.AsyncClient") as MC:
        MC.return_value = _mock_client(SAMPLE_OR_RESPONSE)
        results = await adapter.search("test")
    paper0 = adapter.normalize(results[0])
    paper1 = adapter.normalize(results[1])
    assert paper0.venue == "ICLR 2024"
    assert paper0.year == 2024
    assert paper1.venue == "NeurIPS 2023"
    assert paper1.year == 2023


@pytest.mark.asyncio
async def test_openreview_pdf_url():
    adapter = OpenReviewAdapter()
    with patch("maelstrom.adapters.openreview_adapter.httpx.AsyncClient") as MC:
        MC.return_value = _mock_client(SAMPLE_OR_RESPONSE)
        results = await adapter.search("test")
    paper0 = adapter.normalize(results[0])
    paper1 = adapter.normalize(results[1])
    assert paper0.pdf_url == "https://openreview.net/pdf/abc123note.pdf"
    assert paper1.pdf_url == "https://example.com/paper.pdf"


@pytest.mark.asyncio
async def test_openreview_external_ids():
    adapter = OpenReviewAdapter()
    with patch("maelstrom.adapters.openreview_adapter.httpx.AsyncClient") as MC:
        MC.return_value = _mock_client(SAMPLE_OR_RESPONSE)
        results = await adapter.search("test")
    paper = adapter.normalize(results[0])
    assert paper.external_ids.openreview_id == "abc123note"


@pytest.mark.asyncio
async def test_openreview_timeout():
    adapter = OpenReviewAdapter()
    with patch("maelstrom.adapters.openreview_adapter.httpx.AsyncClient") as MC:
        instance = AsyncMock()
        instance.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MC.return_value = instance
        with pytest.raises(httpx.TimeoutException):
            await adapter.search("test")


@pytest.mark.asyncio
async def test_openreview_api_error():
    adapter = OpenReviewAdapter()
    with patch("maelstrom.adapters.openreview_adapter.httpx.AsyncClient") as MC:
        MC.return_value = _mock_client({}, status_code=500)
        with pytest.raises(httpx.HTTPStatusError):
            await adapter.search("test")
