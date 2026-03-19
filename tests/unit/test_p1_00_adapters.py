"""P1-00: BaseAdapter + ArxivAdapter tests."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest

from maelstrom.adapters.base import BaseAdapter, RawPaperResult
from maelstrom.adapters.arxiv_adapter import ArxivAdapter, _clean_text


# --- Sample Atom XML for mocking ---
SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>  A &amp; B: &lt;b&gt;Bold&lt;/b&gt; Title\n  </title>
    <summary>  Some abstract with\n  whitespace  </summary>
    <published>2024-01-15T10:30:00Z</published>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <link title="pdf" href="http://arxiv.org/pdf/2401.12345v1" />
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.99999v2</id>
    <title>Second Paper</title>
    <summary>Another abstract</summary>
    <published>2024-01-20T08:00:00Z</published>
    <author><name>Carol Lee</name></author>
  </entry>
</feed>"""

EMPTY_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
</feed>"""


def test_base_adapter_abstract():
    """BaseAdapter cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseAdapter()


@pytest.mark.asyncio
async def test_arxiv_search_mock():
    """Mock arXiv API, verify search returns correct count."""
    adapter = ArxivAdapter()
    mock_resp = MagicMock()
    mock_resp.text = SAMPLE_ATOM
    mock_resp.raise_for_status = MagicMock()
    with patch("maelstrom.adapters.arxiv_adapter.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get = AsyncMock(return_value=mock_resp)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        results = await adapter.search("transformer", max_results=10)
    assert len(results) == 2
    assert results[0].raw_id == "2401.12345"
    assert results[1].raw_id == "2401.99999"


@pytest.mark.asyncio
async def test_arxiv_normalize():
    """Verify normalize produces correct PaperRecord fields."""
    adapter = ArxivAdapter()
    raw = RawPaperResult(
        source="arxiv",
        raw_id="2401.12345",
        title="  A &amp; B: <b>Bold</b> Title\n  ",
        authors=["Alice Smith", "Bob Jones"],
        abstract="  Some abstract  ",
        year=2024,
        doi=None,
        pdf_url="http://arxiv.org/pdf/2401.12345v1",
        published_date="2024-01-15T10:30:00Z",
        external_ids={"arxiv_id": "2401.12345"},
    )
    paper = adapter.normalize(raw)
    assert paper.paper_id == "arxiv:2401.12345"
    assert paper.source == "arxiv"
    assert paper.year == 2024
    assert paper.external_ids.arxiv_id == "2401.12345"
    assert len(paper.authors) == 2
    assert paper.authors[0].name == "Alice Smith"
    assert paper.pdf_url == "http://arxiv.org/pdf/2401.12345v1"


def test_arxiv_title_normalization():
    """HTML tags stripped, unicode NFC normalized."""
    assert _clean_text("  A &amp; B: <b>Bold</b> Title\n  ") == "A & B: Bold Title"
    # NFC normalization: combining characters
    assert _clean_text("caf\u0065\u0301") == "caf\u00e9"


def test_arxiv_date_format():
    """Verify year extraction from published date."""
    adapter = ArxivAdapter()
    raw = RawPaperResult(
        source="arxiv", raw_id="2301.00001",
        published_date="2023-06-15T00:00:00Z",
    )
    # Year is parsed during _parse_atom; test normalize preserves it
    raw.year = 2023
    paper = adapter.normalize(raw)
    assert paper.year == 2023


@pytest.mark.asyncio
async def test_arxiv_timeout():
    """Timeout raises httpx.TimeoutException."""
    adapter = ArxivAdapter()
    with patch("maelstrom.adapters.arxiv_adapter.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        with pytest.raises(httpx.TimeoutException):
            await adapter.search("test")


@pytest.mark.asyncio
async def test_arxiv_empty_results():
    """Empty feed returns empty list."""
    adapter = ArxivAdapter()
    mock_resp = MagicMock()
    mock_resp.text = EMPTY_ATOM
    mock_resp.raise_for_status = MagicMock()

    with patch("maelstrom.adapters.arxiv_adapter.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get = AsyncMock(return_value=mock_resp)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        results = await adapter.search("nonexistent_topic_xyz")
    assert results == []
