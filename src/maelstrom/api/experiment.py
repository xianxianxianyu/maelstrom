"""Experiment Engine API endpoints."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from maelstrom.db import session_repo, experiment_run_repo
from maelstrom.db.database import get_db
from maelstrom.services import experiment_service
from maelstrom.services.llm_config_service import get_config

router = APIRouter(prefix="/api/experiment", tags=["experiment"])


@router.get("/runs")
async def list_runs(session_id: str, limit: int = 5):
    db = await get_db()
    runs = await experiment_run_repo.list_by_session(db, session_id, limit=limit)
    return [
        {
            "id": r["id"],
            "session_id": r["session_id"],
            "topic": r["topic"],
            "source_plan_id": r.get("source_plan_id"),
            "status": r["status"],
            "created_at": r["created_at"],
            "completed_at": r.get("completed_at"),
        }
        for r in runs
    ]


@router.post("/run", status_code=202)
async def start_run(body: dict):
    topic = body.get("topic")
    session_id = body.get("session_id")
    plan_id = body.get("plan_id")
    profile_slug = body.get("profile_slug")
    if not session_id or not topic:
        raise HTTPException(status_code=400, detail="session_id and topic required")

    db = await get_db()
    session = await session_repo.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    cfg = get_config()
    if not cfg.profiles:
        raise HTTPException(status_code=400, detail="No profile configured")

    if profile_slug:
        profile = cfg.profiles.get(profile_slug)
        if not profile:
            raise HTTPException(status_code=400, detail=f"Profile '{profile_slug}' not found")
    else:
        profile = cfg.get_active_profile()
        if not profile:
            raise HTTPException(status_code=400, detail="No active profile configured")

    run_id = await experiment_service.start_run(session_id, topic, profile, plan_id=plan_id)
    return {"run_id": run_id}


@router.get("/run/{run_id}/status")
async def get_status(run_id: str):
    status = await experiment_service.get_status(run_id)
    if not status:
        raise HTTPException(status_code=404, detail="Run not found")
    return status


@router.get("/run/{run_id}/result")
async def get_result(run_id: str):
    result = await experiment_service.get_result(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Run not found")
    if result.get("status") in ("pending", "running"):
        raise HTTPException(status_code=409, detail="Run not yet completed")
    if result.get("status") == "failed":
        raise HTTPException(status_code=500, detail="Run failed")
    return result


@router.get("/run/{run_id}/stream")
async def stream_run(run_id: str):
    status = await experiment_service.get_status(run_id)
    if not status:
        raise HTTPException(status_code=404, detail="Run not found")

    # Catch-up: if run already completed/failed, send result immediately
    if status["status"] in ("completed", "failed"):
        await experiment_service.rehydrate_run_state(run_id)

        async def catchup_generator():
            if status["status"] == "completed":
                result = await experiment_service.get_result(run_id)
                yield {"event": "result", "data": result or {}}
            else:
                yield {"event": "error", "data": {"message": "Run failed"}}

        return EventSourceResponse(catchup_generator())

    q = experiment_service.subscribe(run_id)

    # Read checkpoint to replay completed steps
    db = await get_db()
    run = await experiment_run_repo.get_experiment_run(db, run_id)
    completed_steps: list[str] = []
    if run and run.get("progress_json"):
        try:
            progress = json.loads(run["progress_json"])
            completed_steps = progress.get("completed_steps", [])
        except (json.JSONDecodeError, TypeError):
            pass

    async def event_generator():
        for idx, step_name in enumerate(completed_steps):
            yield {"event": "step_complete", "data": {"step": step_name, "summary": f"{step_name} done (replayed)"}}
        try:
            while True:
                event = await q.get()
                if event["event"] == "__done__":
                    break
                yield event
        finally:
            experiment_service.unsubscribe(run_id, q)

    return EventSourceResponse(event_generator())
