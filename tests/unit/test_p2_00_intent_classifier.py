"""P2-00: Intent schema + classifier tests."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from maelstrom.schemas.intent import ClassifiedIntent, IntentType, SessionContext
from maelstrom.services.intent_classifier import (
    _extract_gap_ref,
    _keyword_classify,
    classify_intent,
)


# ── Schema tests ─────────────────────────────────────────────────────


def test_intent_type_has_nine_values():
    assert len(IntentType) == 9
    expected = {
        "gap_discovery", "qa_chat", "gap_followup",
        "share_to_qa", "config", "synthesis", "planning",
        "experiment", "clarification_needed",
    }
    assert {e.value for e in IntentType} == expected


def test_classified_intent_fields():
    ci = ClassifiedIntent(
        intent=IntentType.qa_chat,
        confidence=0.85,
        extracted_topic="NLP",
        extracted_gap_ref=None,
        reasoning="keyword match",
        classifier_source="keyword",
    )
    assert ci.intent == IntentType.qa_chat
    assert ci.confidence == 0.85
    assert ci.extracted_topic == "NLP"
    assert ci.classifier_source == "keyword"


def test_session_context_defaults():
    ctx = SessionContext(session_id="s1")
    assert ctx.has_gap_runs is False
    assert ctx.has_indexed_docs is False
    assert ctx.recent_intent is None


# ── Keyword classifier tests ────────────────────────────────────────


def test_keyword_gap_discovery():
    result = _keyword_classify("帮我分析 NLP 领域的研究空白")
    assert result is not None
    assert result.intent == IntentType.gap_discovery
    assert result.confidence == 0.85
    assert result.classifier_source == "keyword"


def test_keyword_gap_discovery_english():
    result = _keyword_classify("research gap analysis in transformer architectures")
    assert result is not None
    assert result.intent == IntentType.gap_discovery


def test_keyword_gap_discovery_extracts_topic():
    result = _keyword_classify("帮我分析 NLP 领域的研究空白")
    assert result is not None
    assert result.extracted_topic is not None
    assert "NLP" in result.extracted_topic


def test_keyword_gap_discovery_too_short():
    """Short input with gap keyword should not match (< 10 chars)."""
    result = _keyword_classify("研究空白")
    assert result is None  # only 4 chars of content


def test_keyword_qa_chat():
    result = _keyword_classify("这篇论文的方法是什么？")
    assert result is not None
    assert result.intent == IntentType.qa_chat
    assert result.confidence == 0.85


def test_keyword_qa_chat_short_question():
    result = _keyword_classify("什么是 attention？")
    assert result is not None
    assert result.intent == IntentType.qa_chat


def test_keyword_gap_followup_with_context():
    ctx = SessionContext(session_id="s1", has_gap_runs=True)
    result = _keyword_classify("第二个 gap 能展开说说吗", ctx)
    assert result is not None
    assert result.intent == IntentType.gap_followup
    assert result.confidence == 0.85


def test_keyword_gap_followup_explicit_ref():
    result = _keyword_classify("gap-003 能详细说说吗")
    assert result is not None
    assert result.intent == IntentType.gap_followup
    assert result.extracted_gap_ref == "gap-003"


def test_keyword_gap_followup_no_context_no_ref():
    """Without gap runs and no explicit ref, followup keywords alone don't match."""
    result = _keyword_classify("展开说说")
    # No gap context, no explicit gap ref — should not match as gap_followup
    assert result is None or result.intent != IntentType.gap_followup


def test_keyword_share_to_qa():
    result = _keyword_classify("把这些论文加到问答里")
    assert result is not None
    assert result.intent == IntentType.share_to_qa


def test_keyword_config():
    result = _keyword_classify("切换到 Claude 模型")
    assert result is not None
    assert result.intent == IntentType.config


def test_keyword_miss():
    """Ambiguous input should return None (no keyword match)."""
    result = _keyword_classify("我想了解 transformer")
    assert result is None


# ── Gap ref extraction ───────────────────────────────────────────────


def test_extract_gap_ref_explicit():
    assert _extract_gap_ref("gap-003 怎么样") == "gap-003"


def test_extract_gap_ref_ordinal():
    assert _extract_gap_ref("第二个 gap 展开说说") == "gap-2"


def test_extract_gap_ref_none():
    assert _extract_gap_ref("这个方法怎么样") is None


# ── LLM fallback tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_keyword_miss_fallback_llm():
    """When keyword misses, classify_intent should call LLM."""
    mock_response = json.dumps({
        "intent": "gap_discovery",
        "confidence": 0.8,
        "extracted_topic": "transformer architectures",
        "reasoning": "User wants to explore research gaps",
    })
    with patch("maelstrom.services.intent_classifier.get_active_profile_dict", return_value={"protocol": "openai_chat"}):
        with patch("maelstrom.services.intent_classifier.call_llm", new_callable=AsyncMock, return_value=mock_response):
            result = await classify_intent("我想了解 transformer")
            assert result.intent == IntentType.gap_discovery
            assert result.classifier_source == "llm"
            assert result.confidence == 0.8


@pytest.mark.asyncio
async def test_llm_low_confidence_clarification():
    """LLM returning confidence < 0.6 should force clarification_needed."""
    mock_response = json.dumps({
        "intent": "qa_chat",
        "confidence": 0.4,
        "reasoning": "Not sure",
    })
    with patch("maelstrom.services.intent_classifier.get_active_profile_dict", return_value={"protocol": "openai_chat"}):
        with patch("maelstrom.services.intent_classifier.call_llm", new_callable=AsyncMock, return_value=mock_response):
            result = await classify_intent("transformer")
            assert result.intent == IntentType.clarification_needed
            assert result.classifier_source == "llm"


@pytest.mark.asyncio
async def test_llm_timeout_clarification():
    """LLM timeout should return clarification_needed."""
    async def slow_llm(*args, **kwargs):
        await asyncio.sleep(20)
        return "{}"

    with patch("maelstrom.services.intent_classifier.get_active_profile_dict", return_value={"protocol": "openai_chat"}):
        with patch("maelstrom.services.intent_classifier.call_llm", side_effect=slow_llm):
            result = await classify_intent("something ambiguous and long enough")
            assert result.intent == IntentType.clarification_needed
            assert result.classifier_source == "llm"


@pytest.mark.asyncio
async def test_llm_error_clarification():
    """LLM error should return clarification_needed."""
    with patch("maelstrom.services.intent_classifier.get_active_profile_dict", return_value={"protocol": "openai_chat"}):
        with patch("maelstrom.services.intent_classifier.call_llm", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
            result = await classify_intent("something ambiguous and long enough")
            assert result.intent == IntentType.clarification_needed


@pytest.mark.asyncio
async def test_session_context_influence():
    """With gap_runs, followup keywords should classify as gap_followup."""
    ctx = SessionContext(session_id="s1", has_gap_runs=True)
    result = await classify_intent("展开说说", ctx)
    assert result.intent == IntentType.gap_followup


@pytest.mark.asyncio
async def test_keyword_takes_priority_over_llm():
    """Keyword match should return immediately without calling LLM."""
    with patch("maelstrom.services.intent_classifier.call_llm", new_callable=AsyncMock) as mock_llm:
        result = await classify_intent("帮我分析 NLP 领域的研究空白")
        assert result.intent == IntentType.gap_discovery
        assert result.classifier_source == "keyword"
        mock_llm.assert_not_called()
