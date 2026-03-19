"""Phase Router API — unified input endpoint + SSE streaming."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from maelstrom.schemas.router import RouterInput, RouterResponse
from maelstrom.services import phase_router
from maelstrom.services.llm_config_service import get_config
from maelstrom.db.database import get_db
from maelstrom.db import session_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/router", tags=["router"])


@router.post("/input", response_model=RouterResponse)
async def handle_input(body: RouterInput):
    """Unified entry point: classify intent and route to the right engine."""
    response = await phase_router.route(
        session_id=body.session_id,
        user_input=body.user_input,
        clarification_reply=body.clarification_reply,
    )
    return response


@router.post("/input/stream")
async def handle_input_stream(body: RouterInput):
    """Unified entry point with SSE: route + forward target engine's stream."""

    async def event_generator():
        try:
            response = await _route_with_fallback(
                body.session_id, body.user_input, body.clarification_reply,
            )
        except Exception as e:
            logger.exception("Router stream error")
            yield {"event": "error", "data": json.dumps({"message": str(e)})}
            yield {"event": "__done__", "data": "{}"}
            return

        # Emit route_resolved
        intent_value = None
        extracted_topic = None
        if response.intent:
            intent_value = response.intent.intent.value
            extracted_topic = response.intent.extracted_topic
        # Extract run_id from gap stream URL if present
        run_id = None
        if response.stream_url and "/api/gap/run/" in response.stream_url:
            parts = response.stream_url.split("/")
            idx = parts.index("run") + 1 if "run" in parts else -1
            if 0 < idx < len(parts):
                run_id = parts[idx]
        yield {
            "event": "route_resolved",
            "data": json.dumps({
                "response_type": response.response_type,
                "intent": intent_value,
                "confidence": response.intent.confidence if response.intent else None,
                "run_id": run_id,
                "topic": extracted_topic,
            }),
        }

        if response.response_type == "clarification":
            yield {
                "event": "clarification",
                "data": response.clarification.model_dump_json(),
            }
            yield {"event": "__done__", "data": "{}"}
            return

        if response.response_type == "redirect":
            yield {
                "event": "redirect",
                "data": json.dumps({"path": response.redirect_path}),
            }
            yield {"event": "__done__", "data": "{}"}
            return

        if response.response_type == "error":
            yield {
                "event": "error",
                "data": json.dumps({"message": response.error_message}),
            }
            yield {"event": "__done__", "data": "{}"}
            return

        if response.response_type == "stream" and response.stream_url:
            # Forward the target engine's SSE events
            async for event in _proxy_internal_stream(response.stream_url):
                yield event

        # Auto-generate session title if still default
        try:
            db = await get_db()
            session = await session_repo.get_session(db, body.session_id)
            if session and session.get("title", "") in ("Untitled Session", "New Session", ""):
                from maelstrom.services.llm_client import call_llm
                config = get_config()
                profile = config.get_active_profile_or_raise()
                title_prompt = f"用一句简短的中文概括用户意图作为会话标题（不超过20字，只输出标题文字）：{body.user_input}"
                title = await call_llm(title_prompt, profile.model_dump(), max_tokens=50, temperature_override=0.3)
                title = title.strip().strip('"').strip("'")[:40]
                if title:
                    await session_repo.update_session(db, body.session_id, title=title)
                    yield {"event": "session_title", "data": json.dumps({"title": title})}
        except Exception:
            logger.debug("Auto-title generation failed", exc_info=True)

        yield {"event": "__done__", "data": "{}"}

    return EventSourceResponse(event_generator())


async def _route_with_fallback(
    session_id: str,
    user_input: str,
    clarification_reply: dict | None = None,
) -> RouterResponse:
    """Route with error handling and fallback."""
    try:
        # Check LLM config exists
        config = get_config()
        if not config.profiles:
            return RouterResponse(
                response_type="error",
                error_message="请先配置 LLM（设置页面）",
            )
        return await phase_router.route(session_id, user_input, clarification_reply)
    except asyncio.TimeoutError:
        # Classifier timeout — degrade to qa_chat
        logger.warning("Router timeout, degrading to qa_chat")
        from maelstrom.services import chat_service
        msg_id = await chat_service.start_ask(session_id, user_input)
        return RouterResponse(
            response_type="stream",
            stream_url=f"/api/chat/ask/{msg_id}/stream",
        )
    except ValueError as e:
        # LLM config errors
        return RouterResponse(
            response_type="error",
            error_message=f"配置错误: {e}",
        )
    except Exception as e:
        logger.exception("Router error")
        return RouterResponse(
            response_type="error",
            error_message=f"路由失败: {e}",
        )


async def _proxy_internal_stream(stream_url: str):
    """Proxy SSE events from an internal stream URL.

    Instead of making an HTTP request to ourselves, we directly call
    the underlying service's stream generator.
    """
    if "/api/chat/ask/" in stream_url and "/stream" in stream_url:
        # Extract msg_id from URL like /api/chat/ask/{msg_id}/stream
        parts = stream_url.split("/")
        msg_id_idx = parts.index("ask") + 1 if "ask" in parts else -1
        if msg_id_idx > 0 and msg_id_idx < len(parts):
            msg_id = parts[msg_id_idx]
            from maelstrom.services import chat_service
            async for event in chat_service.stream_answer(msg_id):
                yield event
            return

    if "/api/gap/run/" in stream_url and "/stream" in stream_url:
        # Extract run_id from URL like /api/gap/run/{run_id}/stream
        parts = stream_url.split("/")
        run_idx = parts.index("run") + 1 if "run" in parts else -1
        if run_idx > 0 and run_idx < len(parts):
            run_id = parts[run_idx]
            from maelstrom.services import gap_service
            async for event in gap_service.stream_events(run_id):
                yield event
            return

    if "/api/planning/run/" in stream_url and "/stream" in stream_url:
        parts = stream_url.split("/")
        run_idx = parts.index("run") + 1 if "run" in parts else -1
        if run_idx > 0 and run_idx < len(parts):
            run_id = parts[run_idx]
            from maelstrom.services.event_bus import get_event_bus
            bus = get_event_bus()
            q = bus.subscribe(run_id)
            try:
                while True:
                    event = await q.get()
                    if event["event"] == "__done__":
                        break
                    yield event
            finally:
                bus.unsubscribe(run_id, q)
            return

    if "/api/experiment/run/" in stream_url and "/stream" in stream_url:
        parts = stream_url.split("/")
        run_idx = parts.index("run") + 1 if "run" in parts else -1
        if run_idx > 0 and run_idx < len(parts):
            run_id = parts[run_idx]
            from maelstrom.services.event_bus import get_event_bus
            bus = get_event_bus()
            q = bus.subscribe(run_id)
            try:
                while True:
                    event = await q.get()
                    if event["event"] == "__done__":
                        break
                    yield event
            finally:
                bus.unsubscribe(run_id, q)
            return

    # Unknown stream URL — emit error
    yield {"event": "error", "data": json.dumps({"message": f"Unknown stream: {stream_url}"})}
