"""P1-08: coverage_matrix node tests."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from maelstrom.graph.gap_engine import GapEngineState
from maelstrom.graph.nodes.coverage_matrix import coverage_matrix

_PATCH = "maelstrom.graph.nodes.coverage_matrix.call_llm"


def _llm_response(extractions: list[dict]) -> str:
    return json.dumps(extractions)


def _paper(pid: str, title: str = "Paper", abstract: str = "Abstract") -> dict:
    return {"paper_id": pid, "title": title, "abstract": abstract}


SAMPLE_EXTRACTION = [
    {
        "paper_id": "p1",
        "tasks": ["machine translation"],
        "methods": ["Transformer"],
        "datasets": ["WMT14"],
        "metrics": ["BLEU"],
    },
    {
        "paper_id": "p2",
        "tasks": ["machine translation", "summarization"],
        "methods": ["BERT"],
        "datasets": ["WMT14", "CNN/DM"],
        "metrics": ["BLEU", "ROUGE"],
    },
]


@pytest.mark.asyncio
async def test_matrix_structure():
    with patch(_PATCH, new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = _llm_response(SAMPLE_EXTRACTION)
        state: GapEngineState = {
            "papers": [_paper("p1"), _paper("p2")],
            "llm_config": {},
        }
        await coverage_matrix(state)
    cm = state["coverage_matrix"]
    assert "cells" in cm
    assert "summary" in cm
    # Cells have pipe-separated keys with 4 dimensions
    for key in cm["cells"]:
        assert key.count("|") == 3
@pytest.mark.asyncio
async def test_matrix_paper_refs():
    with patch(_PATCH, new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = _llm_response(SAMPLE_EXTRACTION)
        state: GapEngineState = {"papers": [_paper("p1"), _paper("p2")], "llm_config": {}}
        await coverage_matrix(state)
    cells = state["coverage_matrix"]["cells"]
    # p1 should appear in machine translation|Transformer|WMT14|BLEU
    key = "machine translation|Transformer|WMT14|BLEU"
    assert key in cells
    assert "p1" in cells[key]


@pytest.mark.asyncio
async def test_matrix_summary_stats():
    with patch(_PATCH, new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = _llm_response(SAMPLE_EXTRACTION)
        state: GapEngineState = {"papers": [_paper("p1"), _paper("p2")], "llm_config": {}}
        await coverage_matrix(state)
    summary = state["coverage_matrix"]["summary"]
    assert summary["tasks"] == 2  # machine translation, summarization
    assert summary["methods"] == 2  # Transformer, BERT
    assert summary["datasets"] == 2  # WMT14, CNN/DM
    assert summary["metrics"] == 2  # BLEU, ROUGE


@pytest.mark.asyncio
async def test_matrix_empty_cells():
    ext = [{"paper_id": "p1", "tasks": ["A", "B"], "methods": ["M1"],
            "datasets": ["D1"], "metrics": ["Met1"]}]
    with patch(_PATCH, new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = _llm_response(ext)
        state: GapEngineState = {"papers": [_paper("p1")], "llm_config": {}}
        await coverage_matrix(state)
    summary = state["coverage_matrix"]["summary"]
    # 2 tasks * 1 method * 1 dataset * 1 metric = 2 total cells
    assert summary["total_cells"] == 2
    assert summary["filled_cells"] == 2
    assert summary["empty_cells_pct"] == 0.0


@pytest.mark.asyncio
async def test_llm_extraction_mock():
    ext = [{"paper_id": "p1", "tasks": ["NER"], "methods": ["CRF"],
            "datasets": ["CoNLL"], "metrics": ["F1"]}]
    with patch(_PATCH, new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = _llm_response(ext)
        state: GapEngineState = {"papers": [_paper("p1", "NER with CRF", "We use CRF for NER on CoNLL")], "llm_config": {}}
        await coverage_matrix(state)
    cells = state["coverage_matrix"]["cells"]
    assert "NER|CRF|CoNLL|F1" in cells


@pytest.mark.asyncio
async def test_batch_processing():
    """50 papers processed in batches."""
    papers = [_paper(f"p{i}") for i in range(50)]
    ext_per_batch = lambda n: [{"paper_id": f"p{i}", "tasks": ["T"], "methods": ["M"],
                                 "datasets": ["D"], "metrics": ["Met"]} for i in range(n)]

    call_count = 0
    async def _mock_llm(prompt, config, **kwargs):
        nonlocal call_count
        # Count papers in this batch from the prompt (format: [paper_id])
        import re
        count = len(re.findall(r'\[p\d+\]', prompt))
        call_count += 1
        return _llm_response(ext_per_batch(count))

    with patch(_PATCH, new_callable=AsyncMock, side_effect=_mock_llm):
        state: GapEngineState = {"papers": papers, "llm_config": {}}
        await coverage_matrix(state)
    assert call_count == 5  # 50 / 10 = 5 batches
    assert state["coverage_matrix"]["summary"]["filled_cells"] >= 1


@pytest.mark.asyncio
async def test_matrix_no_papers():
    state: GapEngineState = {"papers": [], "llm_config": {}}
    await coverage_matrix(state)
    cm = state["coverage_matrix"]
    assert cm["cells"] == {}
    assert cm["summary"]["tasks"] == 0
