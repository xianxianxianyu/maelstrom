"""P3-09: Synthesis API + Router integration tests."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from maelstrom.services.intent_classifier import classify_intent
from maelstrom.schemas.intent import IntentType, SessionContext
from maelstrom.main import app


# --- Direct endpoint tests (no ASGI client needed) ---

@pytest.mark.asyncio
async def test_start_run_endpoint():
    from maelstrom.api.synthesis import start_run
    from maelstrom.schemas.llm_config import LLMProfile, MaelstromConfig

    profile = LLMProfile(name="openai", model="gpt-4", api_key="test-key")
    config = MaelstromConfig(profiles={"default": profile}, active_profile="default")

    mock_session = {"id": "s1", "title": "Test"}
    with patch("maelstrom.api.synthesis.get_db", new_callable=AsyncMock) as mock_db:
        with patch("maelstrom.api.synthesis.session_repo") as mock_sr:
            mock_sr.get_session = AsyncMock(return_value=mock_session)
            with patch("maelstrom.api.synthesis.get_config", return_value=config):
                with patch("maelstrom.api.synthesis.synthesis_service") as mock_ss:
                    mock_ss.start_run = AsyncMock(return_value="run-1")
                    result = await start_run({"session_id": "s1", "topic": "NER"})
    assert result == {"run_id": "run-1"}


@pytest.mark.asyncio
async def test_status_endpoint():
    from maelstrom.api.synthesis import get_status
    with patch("maelstrom.api.synthesis.synthesis_service") as mock_ss:
        mock_ss.get_status = AsyncMock(return_value={"run_id": "r1", "status": "running", "current_step": "claim_extraction"})
        result = await get_status("r1")
    assert result["status"] == "running"


@pytest.mark.asyncio
async def test_result_not_ready():
    from maelstrom.api.synthesis import get_result
    from fastapi import HTTPException
    with patch("maelstrom.api.synthesis.synthesis_service") as mock_ss:
        mock_ss.get_result = AsyncMock(return_value={"status": "running"})
        with pytest.raises(HTTPException) as exc_info:
            await get_result("r1")
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_claims_endpoint():
    from maelstrom.api.synthesis import get_claims
    with patch("maelstrom.api.synthesis.synthesis_service") as mock_ss:
        mock_ss.get_result = AsyncMock(return_value={"claims": [{"claim_id": "c1"}]})
        result = await get_claims("r1")
    assert len(result) == 1


@pytest.mark.asyncio
async def test_conflicts_endpoint():
    from maelstrom.api.synthesis import get_conflicts
    with patch("maelstrom.api.synthesis.synthesis_service") as mock_ss:
        mock_ss.get_result = AsyncMock(return_value={"consensus_points": [{"s": "x"}], "conflict_points": []})
        result = await get_conflicts("r1")
    assert len(result["consensus_points"]) == 1


@pytest.mark.asyncio
async def test_list_runs():
    from maelstrom.api.synthesis import list_runs
    with patch("maelstrom.api.synthesis.get_db", new_callable=AsyncMock):
        with patch("maelstrom.api.synthesis.synthesis_run_repo") as mock_repo:
            mock_repo.list_by_session = AsyncMock(return_value=[
                {"id": "r1", "session_id": "s1", "topic": "NER", "source_gap_id": None,
                 "status": "completed", "created_at": "2025-01-01", "completed_at": "2025-01-01"}
            ])
            result = await list_runs(session_id="s1", limit=5)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_router_synthesis_intent():
    ctx = SessionContext(session_id="s1")
    intent = await classify_intent("帮我做文献综述", ctx)
    assert intent.intent == IntentType.synthesis


@pytest.mark.asyncio
async def test_api_registered():
    routes = [r.path for r in app.routes]
    assert any("/api/synthesis" in r for r in routes)
