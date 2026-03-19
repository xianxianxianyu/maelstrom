"""Eval repository — CRUD for eval_runs and eval_case_results tables."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import aiosqlite


async def create_eval_run(
    db: aiosqlite.Connection,
    mode: str,
    engine_filter: str | None = None,
    target_run_id: str | None = None,
    target_session_id: str | None = None,
) -> dict:
    eid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO eval_runs (id, mode, status, engine_filter, target_run_id, target_session_id, summary_json, created_at) "
        "VALUES (?, ?, 'pending', ?, ?, ?, '{}', ?)",
        (eid, mode, engine_filter, target_run_id, target_session_id, now),
    )
    await db.commit()
    return {
        "id": eid, "mode": mode, "status": "pending",
        "engine_filter": engine_filter, "target_run_id": target_run_id,
        "target_session_id": target_session_id, "summary_json": "{}",
        "created_at": now, "completed_at": None,
    }


async def get_eval_run(db: aiosqlite.Connection, eval_run_id: str) -> dict | None:
    cur = await db.execute("SELECT * FROM eval_runs WHERE id = ?", (eval_run_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def update_eval_run(
    db: aiosqlite.Connection,
    eval_run_id: str,
    status: str,
    summary_json: str | None = None,
) -> dict | None:
    now = datetime.now(timezone.utc).isoformat()
    if summary_json is not None:
        await db.execute(
            "UPDATE eval_runs SET status = ?, summary_json = ?, completed_at = ? WHERE id = ?",
            (status, summary_json, now if status in ("completed", "failed") else None, eval_run_id),
        )
    else:
        if status in ("completed", "failed"):
            await db.execute(
                "UPDATE eval_runs SET status = ?, completed_at = ? WHERE id = ?",
                (status, now, eval_run_id),
            )
        else:
            await db.execute(
                "UPDATE eval_runs SET status = ? WHERE id = ?",
                (status, eval_run_id),
            )
    await db.commit()
    return await get_eval_run(db, eval_run_id)


async def list_eval_runs(
    db: aiosqlite.Connection, offset: int = 0, limit: int = 20,
) -> tuple[list[dict], int]:
    cur = await db.execute("SELECT COUNT(*) FROM eval_runs")
    row = await cur.fetchone()
    total = row[0] if row else 0
    cur = await db.execute(
        "SELECT * FROM eval_runs ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = [dict(r) for r in await cur.fetchall()]
    return rows, total


async def create_case_result(
    db: aiosqlite.Connection,
    eval_run_id: str,
    case_id: str,
    engine: str,
    passed: bool,
    schema_valid: bool,
    quality_checks_json: str = "{}",
    output_json: str = "{}",
    error: str | None = None,
) -> dict:
    cid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO eval_case_results (id, eval_run_id, case_id, engine, passed, schema_valid, quality_checks_json, output_json, error, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (cid, eval_run_id, case_id, engine, int(passed), int(schema_valid), quality_checks_json, output_json, error, now),
    )
    await db.commit()
    return {
        "id": cid, "eval_run_id": eval_run_id, "case_id": case_id,
        "engine": engine, "passed": int(passed), "schema_valid": int(schema_valid),
        "quality_checks_json": quality_checks_json, "output_json": output_json,
        "error": error, "created_at": now,
    }


async def list_case_results(db: aiosqlite.Connection, eval_run_id: str) -> list[dict]:
    cur = await db.execute(
        "SELECT * FROM eval_case_results WHERE eval_run_id = ? ORDER BY created_at",
        (eval_run_id,),
    )
    return [dict(r) for r in await cur.fetchall()]
