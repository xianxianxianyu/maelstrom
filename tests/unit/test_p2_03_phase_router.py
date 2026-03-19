"""P2-03: Phase Router tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from maelstrom.schemas.intent import ClassifiedIntent, IntentType
from maelstrom.schemas.router import RouterInput, RouterResponse
from maelstrom.services import phase_router


# ── Route tests (mock downstream services) ───────────────────────────


@pytest.mark.asyncio
async def test_route_gap_discovery():
    with patch.object(phase_router, "_build_session_context", new_callable=AsyncMock) as mock_ctx, \
         patch.object(phase_router, "_start_gap_run", new_callable=AsyncMock, return_value="run-001"):
        from maelstrom.schemas.intent import SessionContext
        mock_ctx.return_value = SessionContext(session_id="s1")

        resp = await phase_router.route("s1", "帮我分析 NLP 领域的研究空白")
        assert resp.response_type == "stream"
        assert "/api/gap/" in resp.stream_url
        assert resp.intent.intent == IntentType.gap_discovery


@pytest.mark.asyncio
async def test_route_qa_chat():
    with patch.object(phase_router, "_build_session_context", new_callable=AsyncMock) as mock_ctx, \
         patch.object(phase_router, "_start_qa", new_callable=AsyncMock, return_value="msg-001"):
        from maelstrom.schemas.intent import SessionContext
        mock_ctx.return_value = SessionContext(session_id="s1")

        resp = await phase_router.route("s1", "这篇论文的方法是什么？")
        assert resp.response_type == "stream"
        assert "/api/chat/" in resp.stream_url
        assert resp.intent.intent == IntentType.qa_chat


@pytest.mark.asyncio
async def test_route_config():
    with patch.object(phase_router, "_build_session_context", new_callable=AsyncMock) as mock_ctx:
        from maelstrom.schemas.intent import SessionContext
        mock_ctx.return_value = SessionContext(session_id="s1")

        resp = await phase_router.route("s1", "切换到 Claude 模型")
        assert resp.response_type == "redirect"
        assert resp.redirect_path == "/settings"


@pytest.mark.asyncio
async def test_route_share_to_qa():
    with patch.object(phase_router, "_build_session_context", new_callable=AsyncMock) as mock_ctx:
        from maelstrom.schemas.intent import SessionContext
        mock_ctx.return_value = SessionContext(session_id="s1")

        resp = await phase_router.route("s1", "把论文加到问答里")
        assert resp.response_type == "redirect"
        assert resp.redirect_path == "/gap"


@pytest.mark.asyncio
async def test_route_clarification():
    """Ambiguous input should return clarification."""
    with patch.object(phase_router, "_build_session_context", new_callable=AsyncMock) as mock_ctx, \
         patch("maelstrom.services.intent_classifier.get_active_profile_dict", return_value={"protocol": "openai_chat"}), \
         patch("maelstrom.services.intent_classifier.call_llm", new_callable=AsyncMock, return_value='{"intent":"clarification_needed","confidence":0.3,"reasoning":"unclear"}'):
        from maelstrom.schemas.intent import SessionContext
        mock_ctx.return_value = SessionContext(session_id="s1")

        # Need to also mock the clarification LLM call
        with patch("maelstrom.services.clarification_service.get_active_profile_dict", return_value={"protocol": "openai_chat"}), \
             patch("maelstrom.services.clarification_service.call_llm", new_callable=AsyncMock, side_effect=RuntimeError("no llm")):
            resp = await phase_router.route("s1", "transformer")
            assert resp.response_type == "clarification"
            assert resp.clarification is not None
            assert len(resp.clarification.options) >= 2


@pytest.mark.asyncio
async def test_route_gap_followup():
    with patch.object(phase_router, "_build_session_context", new_callable=AsyncMock) as mock_ctx, \
         patch.object(phase_router, "_start_qa", new_callable=AsyncMock, return_value="msg-002"):
        from maelstrom.schemas.intent import SessionContext
        mock_ctx.return_value = SessionContext(session_id="s1", has_gap_runs=True)

        resp = await phase_router.route("s1", "第一个 gap 展开说说")
        assert resp.response_type == "stream"
        assert resp.intent.intent == IntentType.gap_followup


@pytest.mark.asyncio
async def test_clarification_reply_resolves():
    """Submitting a clarification reply should route to the selected intent."""
    from maelstrom.schemas.clarification import ClarificationOption
    reply = {
        "request_id": "clar-001",
        "option_index": 0,
        "options": [
            {"label": "研究缺口", "intent": "gap_discovery", "description": ""},
            {"label": "问答", "intent": "qa_chat", "description": ""},
        ],
    }
    with patch.object(phase_router, "_start_gap_run", new_callable=AsyncMock, return_value="run-002"):
        resp = await phase_router.route("s1", "", clarification_reply=reply)
        assert resp.response_type == "stream"
        assert "/api/gap/" in resp.stream_url


@pytest.mark.asyncio
async def test_session_context_built():
    """_build_session_context should read from EvidenceMemory."""
    from maelstrom.services.evidence_memory import SessionMemorySummary

    mock_mem = MagicMock()
    mock_mem.get_session_summary = AsyncMock(return_value=SessionMemorySummary(
        session_id="s1", paper_count=5, gap_count=3, total_entries=8,
    ))

    with patch("maelstrom.services.phase_router.get_evidence_memory", return_value=mock_mem):
        ctx = await phase_router._build_session_context("s1")
        assert ctx.has_gap_runs is True
        assert ctx.has_indexed_docs is True


# ── Schema tests ─────────────────────────────────────────────────────


def test_router_input_schema():
    inp = RouterInput(session_id="s1", user_input="hello")
    assert inp.session_id == "s1"
    assert inp.clarification_reply is None


def test_router_response_schema():
    resp = RouterResponse(response_type="redirect", redirect_path="/settings")
    assert resp.response_type == "redirect"
    assert resp.stream_url is None
