"""Eval service — regression, replay, and runtime_metrics modes."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from maelstrom.db import eval_repo, trace_event_repo
from maelstrom.eval.runner import EvalRunner, EvalCase, load_case_from_file

logger = logging.getLogger(__name__)

EVAL_CASES_DIR = os.environ.get(
    "EVAL_CASES_DIR",
    str(Path(__file__).resolve().parents[3] / "tests" / "eval" / "cases"),
)

# Quality criteria by engine for replay mode
_REPLAY_QUALITY = {
    "gap": {"has_ranked_gaps": True},
    "synthesis": {"has_claims": True, "has_review_report": True},
    "planning": {"has_plan": True, "has_hypothesis": True},
    "experiment": {"has_conclusion": True},
}

_ENGINE_TABLES = ["gap_runs", "synthesis_runs", "planning_runs", "experiment_runs"]
_ENGINE_NAMES = ["gap", "synthesis", "planning", "experiment"]


async def start_eval(
    db: aiosqlite.Connection,
    mode: str,
    engine_filter: str | None = None,
    target_run_id: str | None = None,
    target_session_id: str | None = None,
) -> str:
    """Create an eval run and kick off background execution. Returns eval_run_id."""
    run = await eval_repo.create_eval_run(
        db, mode, engine_filter, target_run_id, target_session_id,
    )
    eval_run_id = run["id"]
    asyncio.create_task(_execute_eval(db, eval_run_id, mode, engine_filter, target_run_id, target_session_id))
    return eval_run_id


async def _execute_eval(
    db: aiosqlite.Connection,
    eval_run_id: str,
    mode: str,
    engine_filter: str | None,
    target_run_id: str | None,
    target_session_id: str | None,
) -> None:
    try:
        await eval_repo.update_eval_run(db, eval_run_id, "running")
        if mode == "regression":
            summary = await _run_regression(db, eval_run_id, engine_filter)
        elif mode == "replay":
            summary = await _run_replay(db, eval_run_id, target_run_id, engine_filter)
        elif mode == "runtime_metrics":
            summary = await _run_runtime_metrics(db, eval_run_id, target_run_id, target_session_id)
        else:
            summary = {"error": f"Unknown mode: {mode}"}
        await eval_repo.update_eval_run(db, eval_run_id, "completed", json.dumps(summary))
    except Exception as e:
        logger.exception("Eval run %s failed", eval_run_id)
        await eval_repo.update_eval_run(db, eval_run_id, "failed", json.dumps({"error": str(e)}))


async def _run_regression(db: aiosqlite.Connection, eval_run_id: str, engine_filter: str | None) -> dict:
    cases_dir = Path(EVAL_CASES_DIR)
    cases: list[EvalCase] = []
    if cases_dir.is_dir():
        for fp in sorted(cases_dir.glob("*.json")):
            try:
                case = load_case_from_file(str(fp))
                if engine_filter and case.engine != engine_filter:
                    continue
                cases.append(case)
            except Exception as e:
                logger.warning("Failed to load eval case %s: %s", fp, e)

    runner = EvalRunner()
    suite = await runner.run_suite(cases)

    for r in suite.results:
        await eval_repo.create_case_result(
            db, eval_run_id, r.case_id, _engine_for_case(r.case_id, cases),
            r.passed, r.schema_valid,
            json.dumps(r.quality_checks), json.dumps(r.output), r.error,
        )

    return {"total": suite.total, "passed": suite.passed, "failed": suite.failed}


def _engine_for_case(case_id: str, cases: list[EvalCase]) -> str:
    for c in cases:
        if c.id == case_id:
            return c.engine
    return "unknown"


async def _run_replay(db: aiosqlite.Connection, eval_run_id: str, target_run_id: str | None, engine_filter: str | None) -> dict:
    if not target_run_id:
        return {"error": "target_run_id required for replay mode"}

    runner = EvalRunner()
    total = passed = failed = 0

    for table, engine in zip(_ENGINE_TABLES, _ENGINE_NAMES):
        if engine_filter and engine != engine_filter:
            continue
        cur = await db.execute(f"SELECT * FROM {table} WHERE id = ?", (target_run_id,))
        row = await cur.fetchone()
        if not row:
            continue
        row_dict = dict(row)
        try:
            result_json = json.loads(row_dict.get("result_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            result_json = {}

        schema_valid = bool(result_json)
        criteria = _REPLAY_QUALITY.get(engine, {})
        quality_checks = runner._check_quality(result_json, criteria)
        all_passed = all(quality_checks.values()) if quality_checks else True
        case_passed = schema_valid and all_passed
        total += 1
        if case_passed:
            passed += 1
        else:
            failed += 1

        await eval_repo.create_case_result(
            db, eval_run_id, f"replay-{engine}-{target_run_id[:8]}", engine,
            case_passed, schema_valid, json.dumps(quality_checks), json.dumps(result_json),
        )

    return {"total": total, "passed": passed, "failed": failed}


async def _run_runtime_metrics(
    db: aiosqlite.Connection, eval_run_id: str,
    target_run_id: str | None, target_session_id: str | None,
) -> dict:
    metrics = await compute_runtime_metrics(db, target_run_id, target_session_id)
    return {"metrics": metrics}


async def compute_runtime_metrics(
    db: aiosqlite.Connection,
    run_id: str | None = None,
    session_id: str | None = None,
) -> list[dict]:
    """Aggregate runtime metrics from trace_events."""
    if run_id:
        events = await trace_event_repo.list_by_run(db, run_id)
    elif session_id:
        events = await trace_event_repo.list_by_session(db, session_id)
    else:
        return []

    if not events:
        return []

    # Group events by engine
    by_engine: dict[str, list[dict]] = {}
    for ev in events:
        eng = ev.get("engine", "unknown")
        by_engine.setdefault(eng, []).append(ev)

    results = []
    for engine, eng_events in by_engine.items():
        step_starts: dict[str, str] = {}
        step_durations: dict[str, float] = {}
        error_count = 0
        tool_call_count = 0

        for ev in eng_events:
            et = ev.get("event_type", "")
            node = ev.get("node_name", "")
            ts = ev.get("timestamp", "")

            if et == "step_start" and node:
                step_starts[node] = ts
            elif et == "step_complete" and node and node in step_starts:
                try:
                    t0 = datetime.fromisoformat(step_starts[node])
                    t1 = datetime.fromisoformat(ts)
                    step_durations[node] = (t1 - t0).total_seconds() * 1000
                except (ValueError, TypeError):
                    pass
            elif et == "error":
                error_count += 1
            elif et == "tool_call":
                tool_call_count += 1

        timestamps = [ev.get("timestamp", "") for ev in eng_events if ev.get("timestamp")]
        total_duration_ms = None
        if len(timestamps) >= 2:
            try:
                t_first = datetime.fromisoformat(min(timestamps))
                t_last = datetime.fromisoformat(max(timestamps))
                total_duration_ms = (t_last - t_first).total_seconds() * 1000
            except (ValueError, TypeError):
                pass

        results.append({
            "run_id": run_id,
            "session_id": session_id,
            "engine": engine,
            "total_duration_ms": total_duration_ms,
            "step_durations": step_durations,
            "step_count": len(step_durations),
            "error_count": error_count,
            "tool_call_count": tool_call_count,
        })

    return results
