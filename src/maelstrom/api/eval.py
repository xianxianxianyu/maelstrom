"""Eval API — start eval runs, list results, compute runtime metrics."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query

from maelstrom.db import eval_repo
from maelstrom.db.database import get_db
from maelstrom.schemas.eval import EvalRunRequest, EvalRunOut, EvalCaseResultOut, RuntimeMetricsOut
from maelstrom.services import eval_service

router = APIRouter(prefix="/api/eval", tags=["eval"])


@router.post("/run", status_code=202)
async def start_eval_run(body: EvalRunRequest):
    db = await get_db()
    eval_run_id = await eval_service.start_eval(
        db, body.mode, body.engine_filter, body.target_run_id, body.target_session_id,
    )
    return {"eval_run_id": eval_run_id}


@router.get("/runs")
async def list_eval_runs(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    db = await get_db()
    items, total = await eval_repo.list_eval_runs(db, offset, limit)
    out = []
    for r in items:
        out.append(_format_run(r))
    return {"items": out, "total": total}


@router.get("/run/{eval_run_id}")
async def get_eval_run(eval_run_id: str):
    db = await get_db()
    run = await eval_repo.get_eval_run(db, eval_run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Eval run not found")
    return _format_run(run)


@router.get("/run/{eval_run_id}/results")
async def list_case_results(eval_run_id: str):
    db = await get_db()
    run = await eval_repo.get_eval_run(db, eval_run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Eval run not found")
    rows = await eval_repo.list_case_results(db, eval_run_id)
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "case_id": r["case_id"],
            "engine": r["engine"],
            "passed": bool(r["passed"]),
            "schema_valid": bool(r["schema_valid"]),
            "quality_checks": json.loads(r.get("quality_checks_json", "{}")),
            "error": r.get("error"),
            "created_at": r["created_at"],
        })
    return out


@router.get("/metrics/runtime")
async def get_runtime_metrics(
    run_id: str | None = Query(None),
    session_id: str | None = Query(None),
):
    if not run_id and not session_id:
        raise HTTPException(status_code=400, detail="run_id or session_id required")
    db = await get_db()
    metrics = await eval_service.compute_runtime_metrics(db, run_id, session_id)
    return metrics


def _format_run(r: dict) -> dict:
    summary = r.get("summary_json", "{}")
    if isinstance(summary, str):
        try:
            summary = json.loads(summary)
        except (json.JSONDecodeError, TypeError):
            summary = {}
    return {
        "id": r["id"],
        "mode": r["mode"],
        "status": r["status"],
        "engine_filter": r.get("engine_filter"),
        "target_run_id": r.get("target_run_id"),
        "target_session_id": r.get("target_session_id"),
        "summary": summary,
        "created_at": r["created_at"],
        "completed_at": r.get("completed_at"),
    }
