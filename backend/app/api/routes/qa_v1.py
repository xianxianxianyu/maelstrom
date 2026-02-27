from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from agent.qa_context_v1.kernel import QAContextKernel
from agent.qa_context_v1.models import QueryRequest

router = APIRouter(prefix="/api/qa/v1", tags=["qa-v1"])

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
    docScope: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


class ClarifyPayload(BaseModel):
    sessionId: str
    answer: str = Field(min_length=1)


@router.post("/query")
async def query(payload: QueryPayload) -> dict[str, Any]:
    kernel = _get_kernel()
    try:
        result = await kernel.handle_query(
            QueryRequest(
                query=payload.query,
                session_id=payload.sessionId,
                doc_scope=payload.docScope,
                options=payload.options,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.to_dict()


@router.post("/clarify/{thread_id}")
async def clarify(thread_id: str, payload: ClarifyPayload) -> dict[str, Any]:
    kernel = _get_kernel()
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


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "1.0.0"}
