"""P2-01: Clarification protocol tests."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from maelstrom.schemas.clarification import ClarificationOption, ClarificationRequest
from maelstrom.schemas.intent import ClassifiedIntent, IntentType
from maelstrom.services.clarification_service import (
    _build_template_clarification,
    generate_clarification,
    get_clarification_count,
    reset_clarification_count,
    resolve_clarification,
)


# ── Schema tests ─────────────────────────────────────────────────────


def test_clarification_option_fields():
    opt = ClarificationOption(
        label="发现研究缺口",
        intent=IntentType.gap_discovery,
        description="分析研究空白",
    )
    assert opt.label == "发现研究缺口"
    assert opt.intent == IntentType.gap_discovery


def test_clarification_request_fields():
    req = ClarificationRequest(
        request_id="clar-001",
        question="你想做什么？",
        options=[
            ClarificationOption(label="A", intent=IntentType.qa_chat),
            ClarificationOption(label="B", intent=IntentType.gap_discovery),
        ],
        allow_freetext=True,
        original_input="transformer",
        session_id="s1",
    )
    assert req.request_id == "clar-001"
    assert len(req.options) == 2
    assert req.allow_freetext is True


# ── Template clarification ───────────────────────────────────────────


def test_template_clarification_has_options():
    req = _build_template_clarification("transformer", "s1")
    assert len(req.options) >= 2
    assert req.allow_freetext is True
    assert req.original_input == "transformer"
    assert req.session_id == "s1"


@pytest.mark.asyncio
async def test_template_clarification_mid_confidence():
    """confidence 0.4-0.6 should use template (no LLM call)."""
    reset_clarification_count("s1")
    with patch("maelstrom.services.clarification_service.call_llm", new_callable=AsyncMock) as mock_llm:
        req = await generate_clarification("transformer", "s1", confidence=0.5)
        assert isinstance(req, ClarificationRequest)
        assert len(req.options) >= 2
        mock_llm.assert_not_called()


# ── LLM clarification ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_clarification_low_confidence():
    """confidence < 0.4 should call LLM for clarification."""
    reset_clarification_count("s1")
    mock_response = json.dumps({
        "question": "你想探索什么方向？",
        "options": [
            {"label": "研究缺口", "intent": "gap_discovery", "description": "分析空白"},
            {"label": "问答", "intent": "qa_chat", "description": "文档问答"},
        ],
    })
    with patch("maelstrom.services.clarification_service.get_active_profile_dict", return_value={"protocol": "openai_chat"}):
        with patch("maelstrom.services.clarification_service.call_llm", new_callable=AsyncMock, return_value=mock_response):
            req = await generate_clarification("transformer", "s1", confidence=0.3)
            assert isinstance(req, ClarificationRequest)
            assert req.question == "你想探索什么方向？"
            assert len(req.options) == 2


@pytest.mark.asyncio
async def test_llm_clarification_fallback_on_error():
    """LLM error should fall back to template clarification."""
    reset_clarification_count("s1")
    with patch("maelstrom.services.clarification_service.get_active_profile_dict", return_value={"protocol": "openai_chat"}):
        with patch("maelstrom.services.clarification_service.call_llm", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
            req = await generate_clarification("transformer", "s1", confidence=0.2)
            assert isinstance(req, ClarificationRequest)
            assert len(req.options) >= 2  # template fallback


# ── Resolve clarification ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_option_selection_resolves():
    options = [
        ClarificationOption(label="研究缺口", intent=IntentType.gap_discovery),
        ClarificationOption(label="问答", intent=IntentType.qa_chat),
    ]
    result = await resolve_clarification("s1", "clar-001", option_index=0, options=options)
    assert result.intent == IntentType.gap_discovery
    assert result.confidence == 0.9


@pytest.mark.asyncio
async def test_option_selection_second():
    options = [
        ClarificationOption(label="研究缺口", intent=IntentType.gap_discovery),
        ClarificationOption(label="问答", intent=IntentType.qa_chat),
    ]
    result = await resolve_clarification("s1", "clar-001", option_index=1, options=options)
    assert result.intent == IntentType.qa_chat


@pytest.mark.asyncio
async def test_freetext_reclassify():
    """Freetext should re-classify via classify_intent."""
    reset_clarification_count("s2")
    with patch("maelstrom.services.clarification_service.classify_intent", new_callable=AsyncMock) as mock_classify:
        mock_classify.return_value = ClassifiedIntent(
            intent=IntentType.gap_discovery,
            confidence=0.85,
            classifier_source="keyword",
        )
        result = await resolve_clarification("s2", "clar-001", freetext="帮我分析 NLP 研究空白")
        assert result.intent == IntentType.gap_discovery
        mock_classify.assert_called_once()


@pytest.mark.asyncio
async def test_max_one_clarification():
    """After 2 clarifications, should default to qa_chat."""
    reset_clarification_count("s3")
    # Simulate 2 prior clarifications
    from maelstrom.services.clarification_service import _clarification_counts
    _clarification_counts["s3"] = 2

    result = await resolve_clarification("s3", "clar-002", freetext="still ambiguous")
    assert result.intent == IntentType.qa_chat
    assert "Max clarifications" in result.reasoning

    # Cleanup
    reset_clarification_count("s3")


@pytest.mark.asyncio
async def test_no_option_no_freetext_defaults():
    """No option or freetext should default to qa_chat."""
    result = await resolve_clarification("s1", "clar-001")
    assert result.intent == IntentType.qa_chat


# ── SSE event format ─────────────────────────────────────────────────


def test_sse_event_format():
    """ClarificationRequest should serialize to valid JSON."""
    req = ClarificationRequest(
        request_id="clar-001",
        question="你想做什么？",
        options=[
            ClarificationOption(label="A", intent=IntentType.qa_chat, description="问答"),
            ClarificationOption(label="B", intent=IntentType.gap_discovery, description="缺口"),
        ],
        allow_freetext=True,
        original_input="test",
        session_id="s1",
    )
    data = json.loads(req.model_dump_json())
    assert data["request_id"] == "clar-001"
    assert len(data["options"]) == 2
    assert data["options"][0]["intent"] == "qa_chat"
