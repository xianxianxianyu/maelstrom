"""Phase Router — classify user intent and route to the right engine."""
from __future__ import annotations

import logging

from maelstrom.schemas.clarification import ClarificationRequest
from maelstrom.schemas.intent import ClassifiedIntent, IntentType, SessionContext
from maelstrom.schemas.router import RouterResponse
from maelstrom.services.clarification_service import (
    generate_clarification,
    reset_clarification_count,
    resolve_clarification,
)
from maelstrom.services.evidence_memory import get_evidence_memory
from maelstrom.services.intent_classifier import classify_intent

logger = logging.getLogger(__name__)


async def _build_session_context(session_id: str) -> SessionContext:
    """Build lightweight session context from EvidenceMemory + synthesis_runs."""
    try:
        mem = get_evidence_memory()
        summary = await mem.get_session_summary(session_id)
        # Check synthesis runs
        has_synthesis = False
        try:
            from maelstrom.db import synthesis_run_repo
            from maelstrom.db.database import get_db
            db = await get_db()
            count = await synthesis_run_repo.count_by_session(db, session_id)
            has_synthesis = count > 0
        except Exception:
            pass
        return SessionContext(
            session_id=session_id,
            has_gap_runs=summary.gap_count > 0,
            has_indexed_docs=summary.paper_count > 0,
            has_synthesis_runs=has_synthesis,
        )
    except Exception:
        return SessionContext(session_id=session_id)


async def route(
    session_id: str,
    user_input: str,
    clarification_reply: dict | None = None,
) -> RouterResponse:
    """Route user input to the appropriate engine/service."""

    # ── Handle clarification reply ────────────────────────────────
    if clarification_reply:
        intent = await _resolve_clarification_reply(session_id, clarification_reply)
    else:
        context = await _build_session_context(session_id)
        intent = await classify_intent(user_input, context)

    # ── Route based on intent ─────────────────────────────────────
    if intent.intent == IntentType.clarification_needed:
        clar = await generate_clarification(
            user_input, session_id, confidence=intent.confidence,
        )
        return RouterResponse(
            response_type="clarification",
            clarification=clar,
            intent=intent,
        )

    # Successful classification — reset clarification counter
    reset_clarification_count(session_id)

    if intent.intent == IntentType.gap_discovery:
        topic = intent.extracted_topic or user_input
        run_id = await _start_gap_run(session_id, topic)
        return RouterResponse(
            response_type="stream",
            stream_url=f"/api/gap/run/{run_id}/stream",
            intent=intent,
        )

    if intent.intent == IntentType.qa_chat:
        msg_id = await _start_qa(session_id, user_input)
        return RouterResponse(
            response_type="stream",
            stream_url=f"/api/chat/ask/{msg_id}/stream",
            intent=intent,
        )

    if intent.intent == IntentType.gap_followup:
        msg_id = await _start_qa(session_id, user_input)
        return RouterResponse(
            response_type="stream",
            stream_url=f"/api/chat/ask/{msg_id}/stream",
            intent=intent,
        )

    if intent.intent == IntentType.share_to_qa:
        return RouterResponse(
            response_type="redirect",
            redirect_path="/gap",
            intent=intent,
        )

    if intent.intent == IntentType.config:
        return RouterResponse(
            response_type="redirect",
            redirect_path="/settings",
            intent=intent,
        )

    if intent.intent == IntentType.synthesis:
        topic = intent.extracted_topic or user_input
        # Extract latest gap run ID for gap→synthesis linkage
        gap_id = None
        try:
            from maelstrom.db import gap_run_repo
            from maelstrom.db.database import get_db as _get_db
            _db = await _get_db()
            latest_gap = await gap_run_repo.latest_by_session(_db, session_id)
            if latest_gap and latest_gap["status"] == "completed":
                gap_id = latest_gap["id"]
        except Exception:
            pass
        run_id = await _start_synthesis_run(session_id, topic, gap_id=gap_id)
        return RouterResponse(
            response_type="stream",
            stream_url=f"/api/synthesis/run/{run_id}/stream",
            intent=intent,
        )

    if intent.intent == IntentType.planning:
        topic = intent.extracted_topic or user_input
        # Extract latest synthesis run ID for synthesis→planning linkage
        synthesis_id = None
        try:
            from maelstrom.db import synthesis_run_repo
            from maelstrom.db.database import get_db as _get_db
            _db = await _get_db()
            latest_syn = await synthesis_run_repo.latest_by_session(_db, session_id)
            if latest_syn and latest_syn["status"] == "completed":
                synthesis_id = latest_syn["id"]
        except Exception:
            pass
        run_id = await _start_planning_run(session_id, topic, synthesis_id=synthesis_id)
        return RouterResponse(
            response_type="stream",
            stream_url=f"/api/planning/run/{run_id}/stream",
            intent=intent,
        )

    if intent.intent == IntentType.experiment:
        topic = intent.extracted_topic or user_input
        # Extract latest planning run ID for planning→experiment linkage
        plan_id = None
        try:
            from maelstrom.db import planning_run_repo
            from maelstrom.db.database import get_db as _get_db
            _db = await _get_db()
            latest_plan = await planning_run_repo.latest_by_session(_db, session_id)
            if latest_plan and latest_plan["status"] == "completed":
                plan_id = latest_plan["id"]
        except Exception:
            pass
        run_id = await _start_experiment_run(session_id, topic, plan_id=plan_id)
        return RouterResponse(
            response_type="stream",
            stream_url=f"/api/experiment/run/{run_id}/stream",
            intent=intent,
        )

    # Fallback
    return RouterResponse(
        response_type="error",
        error_message="Unknown intent",
        intent=intent,
    )


async def _resolve_clarification_reply(
    session_id: str,
    reply: dict,
) -> ClassifiedIntent:
    """Parse a clarification reply dict into a ClassifiedIntent."""
    request_id = reply.get("request_id", "")
    option_index = reply.get("option_index")
    freetext = reply.get("freetext")
    options_raw = reply.get("options")

    # Reconstruct options if provided
    from maelstrom.schemas.clarification import ClarificationOption
    options = None
    if options_raw:
        options = [ClarificationOption.model_validate(o) for o in options_raw]

    return await resolve_clarification(
        session_id, request_id, option_index, freetext, options,
    )


async def _start_gap_run(session_id: str, topic: str) -> str:
    """Start a gap engine run and return run_id."""
    from maelstrom.services import gap_service
    from maelstrom.services.llm_config_service import get_config

    config = get_config()
    profile = config.get_active_profile_or_raise()
    return await gap_service.start_run(session_id, topic, profile)


async def _start_qa(session_id: str, question: str) -> str:
    """Start a QA chat task and return msg_id."""
    from maelstrom.services import chat_service

    return await chat_service.start_ask(session_id, question)


async def _start_synthesis_run(session_id: str, topic: str, gap_id: str | None = None) -> str:
    """Start a synthesis engine run and return run_id."""
    from maelstrom.services import synthesis_service
    from maelstrom.services.llm_config_service import get_config

    config = get_config()
    profile = config.get_active_profile_or_raise()
    return await synthesis_service.start_run(session_id, topic, profile, gap_id=gap_id)


async def _start_planning_run(session_id: str, topic: str, synthesis_id: str | None = None) -> str:
    """Start a planning engine run and return run_id."""
    from maelstrom.services import planning_service
    from maelstrom.services.llm_config_service import get_config

    config = get_config()
    profile = config.get_active_profile_or_raise()
    return await planning_service.start_run(session_id, topic, profile, synthesis_id=synthesis_id)


async def _start_experiment_run(session_id: str, topic: str, plan_id: str | None = None) -> str:
    """Start an experiment engine run and return run_id."""
    from maelstrom.services import experiment_service
    from maelstrom.services.llm_config_service import get_config

    config = get_config()
    profile = config.get_active_profile_or_raise()
    return await experiment_service.start_run(session_id, topic, profile, plan_id=plan_id)
