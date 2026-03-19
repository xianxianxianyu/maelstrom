"""P1-06: topic_intake + query_expansion node tests."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from maelstrom.graph.gap_engine import GapEngineState
from maelstrom.graph.nodes.topic_intake import topic_intake
from maelstrom.graph.nodes.query_expansion import query_expansion

_PATCH_TARGET = "maelstrom.graph.nodes.query_expansion.call_llm"


# --- topic_intake tests ---

def test_topic_intake_valid():
    state: GapEngineState = {"topic": "transformer efficiency in NLP"}
    result = topic_intake(state)
    assert result.get("error") is None
    assert result["current_step"] == "topic_intake"


def test_topic_intake_empty():
    state: GapEngineState = {"topic": ""}
    result = topic_intake(state)
    assert result["error"] == "Topic is required"


def test_topic_intake_too_short():
    state: GapEngineState = {"topic": "short"}
    result = topic_intake(state)
    assert "too short" in result["error"]


def test_topic_intake_none():
    state: GapEngineState = {}
    result = topic_intake(state)
    assert result["error"] == "Topic is required"


# --- query_expansion tests ---

@pytest.mark.asyncio
async def test_query_expansion_count():
    """Mock LLM returns 4 queries, total should be 5 (original + 4)."""
    llm_response = json.dumps([
        "efficiency of transformers",
        "attention mechanism optimization",
        "lightweight NLP models",
        "transformer inference speed",
    ])
    with patch(_PATCH_TARGET, new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = llm_response
        state: GapEngineState = {
            "topic": "transformer efficiency in NLP",
            "llm_config": {"provider": "openai", "model_name": "gpt-4o", "api_key": "sk-test"},
        }
        result = await query_expansion(state)
    assert 3 <= len(result["expanded_queries"]) <= 6
@pytest.mark.asyncio
async def test_query_expansion_includes_original():
    """expanded_queries always includes the original topic."""
    llm_response = json.dumps(["query A", "query B", "query C"])
    with patch(_PATCH_TARGET, new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = llm_response
        state: GapEngineState = {
            "topic": "transformer efficiency in NLP",
            "llm_config": {},
        }
        result = await query_expansion(state)
    assert result["expanded_queries"][0] == "transformer efficiency in NLP"


@pytest.mark.asyncio
async def test_query_expansion_diversity():
    """All generated queries are unique."""
    llm_response = json.dumps([
        "efficient transformers",
        "attention pruning methods",
        "model compression NLP",
        "fast inference transformers",
    ])
    with patch(_PATCH_TARGET, new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = llm_response
        state: GapEngineState = {
            "topic": "transformer efficiency",
            "llm_config": {},
        }
        result = await query_expansion(state)
    queries = result["expanded_queries"]
    assert len(queries) == len(set(queries))


@pytest.mark.asyncio
async def test_query_expansion_llm_config():
    """LLM is called with the config from state."""
    with patch(_PATCH_TARGET, new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = '["q1", "q2", "q3"]'
        cfg = {"provider": "anthropic", "model_name": "claude-sonnet-4-6", "api_key": "sk-ant"}
        state: GapEngineState = {"topic": "test topic here", "llm_config": cfg}
        await query_expansion(state)
    call_args = mock_llm.call_args
    assert call_args[0][1] == cfg  # second positional arg is llm_config


@pytest.mark.asyncio
async def test_query_expansion_llm_error():
    """LLM failure falls back to original topic only."""
    with patch(_PATCH_TARGET, new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = RuntimeError("API down")
        state: GapEngineState = {
            "topic": "transformer efficiency in NLP",
            "llm_config": {},
        }
        result = await query_expansion(state)
    assert result["expanded_queries"] == ["transformer efficiency in NLP"]
    assert result.get("error") is None  # Not a fatal error
