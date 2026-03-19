from fastapi import APIRouter, Depends, HTTPException, Response

from maelstrom.api.session_models import CreateSessionRequest, SessionResponse, SessionUpdateRequest
from maelstrom.db.database import get_db
from maelstrom.db import session_repo, artifact_repo, chat_repo, gap_run_repo
from maelstrom.db import synthesis_run_repo, planning_run_repo, experiment_run_repo
from maelstrom.services.auth_middleware import get_optional_user
from maelstrom.services.phase_tracker import get_current_phase

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(req: CreateSessionRequest | None = None):
    db = await get_db()
    title = req.title if req else "Untitled Session"
    s = await session_repo.create_session(db, title=title)
    return s


@router.get("", response_model=list[SessionResponse])
async def list_sessions(user: dict | None = Depends(get_optional_user)):
    db = await get_db()
    if user:
        sessions = await session_repo.list_sessions_by_user(db, user["id"])
    else:
        sessions = await session_repo.list_sessions(db)
    enriched = []
    for s in sessions:
        sid = s["id"]
        run_count = await gap_run_repo.count_by_session(db, sid)
        latest_run = await gap_run_repo.latest_by_session(db, sid)
        message_count = await chat_repo.count_by_session(db, sid)
        phase = await get_current_phase(sid)
        enriched.append({
            **s,
            "run_count": run_count,
            "latest_run_status": latest_run["status"] if latest_run else None,
            "latest_run_topic": latest_run["topic"] if latest_run else None,
            "message_count": message_count,
            "current_phase": phase.value,
        })
    return enriched


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    db = await get_db()
    s = await session_repo.get_session(db, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return s


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(session_id: str, req: SessionUpdateRequest):
    db = await get_db()
    s = await session_repo.get_session(db, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    updates = {}
    if req.title is not None:
        updates["title"] = req.title
    if not updates:
        return s
    updated = await session_repo.update_session(db, session_id, **updates)
    return updated


@router.get("/{session_id}/history")
async def get_session_history(session_id: str):
    """Return chat history in assistant-ui ThreadMessageLike format."""
    db = await get_db()
    s = await session_repo.get_session(db, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    rows = await chat_repo.list_messages_by_session(db, session_id)
    messages = []
    for r in rows:
        messages.append({
            "role": r["role"],
            "content": [{"type": "text", "text": r["content"]}],
        })
    return {"messages": messages}


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str):
    db = await get_db()
    deleted = await session_repo.delete_session(db, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return Response(status_code=204)


@router.get("/{session_id}/phase")
async def get_session_phase(session_id: str):
    db = await get_db()
    s = await session_repo.get_session(db, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    phase = await get_current_phase(session_id)
    return {"session_id": session_id, "current_phase": phase.value}


@router.get("/{session_id}/workspace")
async def get_workspace(session_id: str):
    db = await get_db()
    s = await session_repo.get_session(db, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    phase = await get_current_phase(session_id)
    gap_runs = await gap_run_repo.list_by_session(db, session_id, limit=20)
    syn_runs = await synthesis_run_repo.list_by_session(db, session_id, limit=20)
    plan_runs = await planning_run_repo.list_by_session(db, session_id, limit=20)
    exp_runs = await experiment_run_repo.list_by_session(db, session_id, limit=20)
    return {
        "session_id": session_id,
        "title": s.get("title", ""),
        "current_phase": phase.value,
        "gap_runs": [{"id": r["id"], "topic": r["topic"], "status": r["status"], "created_at": r["created_at"]} for r in gap_runs],
        "synthesis_runs": [{"id": r["id"], "topic": r["topic"], "status": r["status"], "created_at": r["created_at"]} for r in syn_runs],
        "planning_runs": [{"id": r["id"], "topic": r["topic"], "status": r["status"], "created_at": r["created_at"]} for r in plan_runs],
        "experiment_runs": [{"id": r["id"], "topic": r["topic"], "status": r["status"], "created_at": r["created_at"]} for r in exp_runs],
    }
