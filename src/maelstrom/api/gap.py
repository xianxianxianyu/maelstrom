"""Gap Engine API endpoints."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from maelstrom.db import session_repo, gap_run_repo
from maelstrom.db.database import get_db
from maelstrom.services import gap_service
from maelstrom.services.doc_service import share_papers_to_qa
from maelstrom.services.llm_config_service import get_config

router = APIRouter(prefix="/api/gap", tags=["gap"])


@router.get("/runs")
async def list_runs(session_id: str, limit: int = 1):
    """List gap runs for a session, most recent first."""
    db = await get_db()
    runs = await gap_run_repo.list_by_session(db, session_id, limit=limit)
    return [
        {
            "id": r["id"],
            "session_id": r["session_id"],
            "topic": r["topic"],
            "status": r["status"],
            "created_at": r["created_at"],
            "completed_at": r["completed_at"],
        }
        for r in runs
    ]


@router.post("/run", status_code=202)
async def start_run(body: dict):
    topic = body.get("topic")
    session_id = body.get("session_id")
    profile_slug = body.get("profile_slug")
    if not topic or not session_id:
        raise HTTPException(status_code=400, detail="topic and session_id required")

    db = await get_db()
    session = await session_repo.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    cfg = get_config()
    if not cfg.profiles:
        raise HTTPException(status_code=400, detail="No profile configured")

    # Resolve profile: explicit slug > active_profile
    if profile_slug:
        profile = cfg.profiles.get(profile_slug)
        if not profile:
            raise HTTPException(status_code=400, detail=f"Profile '{profile_slug}' not found")
    else:
        profile = cfg.get_active_profile()
        profile_slug = cfg.active_profile
        if not profile:
            raise HTTPException(
                status_code=400,
                detail=f"Active profile '{cfg.active_profile}' not found",
            )

    if not profile.api_key:
        raise HTTPException(
            status_code=400,
            detail=f"Profile '{profile_slug}' has no API key configured",
        )

    run_id = await gap_service.start_run(session_id, topic, profile)
    return {"run_id": run_id}


@router.get("/run/{run_id}/status")
async def get_status(run_id: str):
    status = await gap_service.get_status(run_id)
    if not status:
        raise HTTPException(status_code=404, detail="Run not found")
    return status


@router.get("/run/{run_id}/result")
async def get_result(run_id: str):
    result = await gap_service.get_result(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Run not found")
    if result.get("status") in ("pending", "running"):
        raise HTTPException(status_code=409, detail="Run not yet completed")
    if result.get("status") == "failed":
        raise HTTPException(status_code=500, detail="Run failed")
    return result


@router.get("/run/{run_id}/papers")
async def get_papers(run_id: str, offset: int = 0, limit: int = 50):
    status = await gap_service.get_status(run_id)
    if not status:
        raise HTTPException(status_code=404, detail="Run not found")
    papers = await gap_service.get_papers(run_id, offset=offset, limit=limit)
    return {"papers": papers, "offset": offset, "limit": limit}


@router.get("/run/{run_id}/matrix")
async def get_matrix(run_id: str):
    status = await gap_service.get_status(run_id)
    if not status:
        raise HTTPException(status_code=404, detail="Run not found")
    matrix = await gap_service.get_matrix(run_id)
    if matrix is None:
        raise HTTPException(status_code=409, detail="Matrix not yet available")
    return matrix


@router.get("/run/{run_id}/stream")
async def stream_run(run_id: str):
    status = await gap_service.get_status(run_id)
    if not status:
        raise HTTPException(status_code=404, detail="Run not found")

    # Catch-up: if run already completed/failed, send result immediately
    if status["status"] in ("completed", "failed"):
        await gap_service.rehydrate_run_state(run_id)

        async def catchup_generator():
            if status["status"] == "completed":
                result = await gap_service.get_result(run_id)
                yield {"event": "result", "data": result or {}}
            else:
                yield {"event": "error", "data": {"message": "Run failed"}}

        return EventSourceResponse(catchup_generator())

    q = gap_service.subscribe(run_id)

    # Read checkpoint to replay completed steps
    db = await get_db()
    run = await gap_run_repo.get_gap_run(db, run_id)
    completed_steps: list[str] = []
    if run and run.get("progress_json"):
        try:
            progress = json.loads(run["progress_json"])
            completed_steps = progress.get("completed_steps", [])
        except (json.JSONDecodeError, TypeError):
            pass

    async def event_generator():
        # Replay already-completed steps so frontend can mark them done
        for idx, step_name in enumerate(completed_steps):
            yield {"event": "step_complete", "data": {"step": step_name, "summary": f"{step_name} done (replayed)"}}
        try:
            while True:
                event = await q.get()
                if event["event"] == "__done__":
                    break
                yield event
        finally:
            gap_service.unsubscribe(run_id, q)

    return EventSourceResponse(event_generator())


@router.post("/run/{run_id}/share-to-qa")
async def share_to_qa(run_id: str, body: dict):
    """Share papers from a gap run into the QA Chat index."""
    session_id = body.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    result = await gap_service.get_result(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Run not found")
    # get_result returns {"status": ...} for non-completed runs,
    # and the raw result dict (no "status" key) for completed runs.
    if "status" in result:
        if result["status"] == "failed":
            raise HTTPException(status_code=500, detail="Run failed")
        raise HTTPException(status_code=409, detail="Run not yet completed")

    papers = result.get("papers", [])
    if not papers:
        return {"shared": 0, "failed": 0, "skipped": 0}

    summary = await share_papers_to_qa(session_id, papers)
    return summary
