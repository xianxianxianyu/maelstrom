from __future__ import annotations

import os
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from agent.qa_context_v1.kernel import QAContextKernel
from agent.qa_context_v1.models import QueryRequest

router = APIRouter(prefix="/api/qa/v1", tags=["qa-v1"])
logger = logging.getLogger(__name__)

_kernel: QAContextKernel | None = None


def _get_kernel() -> QAContextKernel:
    global _kernel
    if _kernel is None:
        base_dir = os.getenv("QA_V1_CONTEXT_DIR", "data/qa_v1/sessions")
        _kernel = QAContextKernel.create_default(base_dir=base_dir)
    return _kernel


class QueryPayload(BaseModel):
    query: str = Field(min_length=1)
    sessionId: str | None = None
    traceId: str | None = None
    docScope: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


class ClarifyPayload(BaseModel):
    sessionId: str
    answer: str = Field(min_length=1)


@router.post("/query")
async def query(payload: QueryPayload) -> dict[str, Any]:
    kernel = _get_kernel()
    logger.info(
        "qa query received",
        extra={
            "trace_id": payload.traceId,
            "session_id": payload.sessionId,
            "query_len": len(payload.query),
            "doc_scope_size": len(payload.docScope),
        },
    )
    try:
        result = await kernel.handle_query(
            QueryRequest(
                query=payload.query,
                session_id=payload.sessionId,
                trace_id=payload.traceId,
                doc_scope=payload.docScope,
                options=payload.options,
            )
        )
    except ValueError as exc:
        logger.warning(
            "qa query validation failed",
            extra={"trace_id": payload.traceId, "session_id": payload.sessionId, "error": str(exc)},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "qa query completed",
        extra={
            "trace_id": result.trace_id,
            "session_id": result.session_id,
            "turn_id": result.turn_id,
            "status": result.status,
            "confidence": result.confidence,
            "has_clarification": result.status == "clarification_pending",
        },
    )
    return result.to_dict()


@router.post("/clarify/{thread_id}")
async def clarify(thread_id: str, payload: ClarifyPayload) -> dict[str, Any]:
    kernel = _get_kernel()
    logger.info(
        "qa clarification received",
        extra={"session_id": payload.sessionId, "thread_id": thread_id, "answer_len": len(payload.answer)},
    )
    try:
        result = await kernel.handle_clarification(
            session_id=payload.sessionId,
            thread_id=thread_id,
            answer=payload.answer,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "qa clarification completed",
        extra={"session_id": result.session_id, "turn_id": result.turn_id, "status": result.status},
    )
    return result.to_dict()


@router.get("/sessions/{session_id}/turns")
async def list_turns(session_id: str, limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    kernel = _get_kernel()
    return {"session_id": session_id, "turns": kernel.list_turns(session_id=session_id, limit=limit)}


@router.get("/turns/{turn_id}")
async def get_turn(turn_id: str, session_id: str = Query(...)) -> dict[str, Any]:
    kernel = _get_kernel()
    turn = kernel.get_turn(session_id=session_id, turn_id=turn_id)
    if turn is None:
        raise HTTPException(status_code=404, detail="turn not found")
    return turn


@router.get("/execution/{trace_id}")
async def get_execution(trace_id: str) -> dict[str, Any]:
    kernel = _get_kernel()
    snapshot = kernel.get_execution_snapshot(trace_id)
    if snapshot is None:
        logger.warning("qa execution snapshot missing", extra={"trace_id": trace_id})
        raise HTTPException(status_code=404, detail="execution trace not found")
    logger.info("qa execution snapshot fetched", extra={"trace_id": trace_id})
    return snapshot


@router.get("/execution/{trace_id}/events")
async def get_execution_events(trace_id: str) -> dict[str, Any]:
    kernel = _get_kernel()
    return {"trace_id": trace_id, "events": kernel.get_execution_events(trace_id)}


@router.post("/execution/{trace_id}/retry")
async def retry_execution(trace_id: str) -> dict[str, Any]:
    kernel = _get_kernel()
    logger.info("qa execution retry requested", extra={"trace_id": trace_id})
    try:
        result = await kernel.retry_execution(trace_id)
    except KeyError as exc:
        logger.warning("qa execution retry miss", extra={"trace_id": trace_id, "error": str(exc)})
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("qa retry failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    logger.info(
        "qa execution retry completed",
        extra={"trace_id": trace_id, "new_trace_id": result.trace_id, "status": result.status},
    )
    return result.to_dict()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "1.0.0"}
