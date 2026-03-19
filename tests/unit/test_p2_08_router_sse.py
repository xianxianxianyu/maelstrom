"""P2-08: Router SSE + error handling tests."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from maelstrom.api.router import _route_with_fallback
from maelstrom.schemas.intent import ClassifiedIntent, IntentType
from maelstrom.schemas.router import RouterResponse


@pytest.mark.asyncio
async def test_fallback_no_llm_config():
    """No LLM profiles → error response."""
    mock_config = MagicMock()
    mock_config.profiles = {}
    with patch("maelstrom.api.router.get_config", return_value=mock_config):
        resp = await _route_with_fallback("s1", "test input")
        assert resp.response_type == "error"
        assert "配置 LLM" in resp.error_message


@pytest.mark.asyncio
async def test_fallback_classifier_timeout():
    """Classifier timeout → degrade to qa_chat stream."""
    import asyncio
    mock_config = MagicMock()
    mock_config.profiles = {"default": MagicMock()}

    with patch("maelstrom.api.router.get_config", return_value=mock_config), \
         patch("maelstrom.api.router.phase_router.route", new_callable=AsyncMock, side_effect=asyncio.TimeoutError()), \
         patch("maelstrom.services.chat_service.start_ask", new_callable=AsyncMock, return_value="msg-fallback"):
        resp = await _route_with_fallback("s1", "test input")
        assert resp.response_type == "stream"
        assert "/api/chat/" in resp.stream_url


@pytest.mark.asyncio
async def test_fallback_value_error():
    """ValueError (config error) → error response."""
    mock_config = MagicMock()
    mock_config.profiles = {"default": MagicMock()}

    with patch("maelstrom.api.router.get_config", return_value=mock_config), \
         patch("maelstrom.api.router.phase_router.route", new_callable=AsyncMock, side_effect=ValueError("bad config")):
        resp = await _route_with_fallback("s1", "test input")
        assert resp.response_type == "error"
        assert "配置错误" in resp.error_message


@pytest.mark.asyncio
async def test_fallback_generic_exception():
    """Unknown exception → error response with message."""
    mock_config = MagicMock()
    mock_config.profiles = {"default": MagicMock()}

    with patch("maelstrom.api.router.get_config", return_value=mock_config), \
         patch("maelstrom.api.router.phase_router.route", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
        resp = await _route_with_fallback("s1", "test input")
        assert resp.response_type == "error"
        assert "路由失败" in resp.error_message


@pytest.mark.asyncio
async def test_fallback_success_passthrough():
    """Normal route → passthrough."""
    mock_config = MagicMock()
    mock_config.profiles = {"default": MagicMock()}
    expected = RouterResponse(
        response_type="redirect",
        redirect_path="/settings",
        intent=ClassifiedIntent(intent=IntentType.config, confidence=0.85),
    )

    with patch("maelstrom.api.router.get_config", return_value=mock_config), \
         patch("maelstrom.api.router.phase_router.route", new_callable=AsyncMock, return_value=expected):
        resp = await _route_with_fallback("s1", "切换模型")
        assert resp.response_type == "redirect"
        assert resp.redirect_path == "/settings"
