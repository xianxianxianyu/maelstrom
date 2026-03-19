from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from maelstrom.db import session_repo, chat_repo
from maelstrom.db.database import get_db
from maelstrom.services import chat_service, phase_router

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/messages")
async def list_messages(session_id: str):
    """Return chat history for a session."""
    db = await get_db()
    session = await session_repo.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    rows = await chat_repo.list_messages_by_session(db, session_id)
    return [
        {
            "id": r["id"],
            "role": r["role"],
            "content": r["content"],
            "citations_json": r["citations_json"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@router.post("/ask", status_code=202)
async def ask(body: dict):
    session_id = body.get("session_id")
    question = body.get("question")
    if not session_id or not question:
        raise HTTPException(status_code=400, detail="session_id and question required")

    db = await get_db()
    session = await session_repo.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    msg_id = await chat_service.start_ask(session_id, question)
    return {"msg_id": msg_id}


@router.get("/ask/{msg_id}/stream")
async def stream(msg_id: str):
    task = chat_service.get_task(msg_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator():
        async for event in chat_service.stream_answer(msg_id):
            yield event

    return EventSourceResponse(event_generator())


class ClarifyInput(BaseModel):
    session_id: str
    request_id: str
    option_index: int | None = None
    freetext: str | None = None


@router.post("/clarify")
async def clarify(body: ClarifyInput):
    """Handle user reply to a clarification request."""
    response = await phase_router.route(
        session_id=body.session_id,
        user_input=body.freetext or "",
        clarification_reply={
            "request_id": body.request_id,
            "option_index": body.option_index,
            "freetext": body.freetext,
        },
    )
    return response
