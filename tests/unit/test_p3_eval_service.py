"""P3 Eval Service — unit tests for eval_service logic."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import aiosqlite
import pytest

from maelstrom.db.migrations import run_migrations
from maelstrom.db import eval_repo, trace_event_repo
from maelstrom.eval.runner import EvalCase, EvalResult, EvalSuiteResult
from maelstrom.services import eval_service


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await run_migrations(conn)
    # Create a test session
    now = datetime.now(timezone.utc).isoformat()
    await conn.execute(
        "INSERT INTO sessions (id, title, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("s1", "Test", "active", now, now),
    )
    await conn.commit()
    yield conn
    await conn.close()


@pytest.mark.asyncio
async def test_regression_mode(db):
    """Mock EvalRunner.run_suite and verify case results are written."""
    fake_suite = EvalSuiteResult(
        total=2, passed=1, failed=1,
        results=[
            EvalResult(case_id="c1", passed=True, schema_valid=True, quality_checks={"has_gaps": True}, output={"gaps": [1]}),
            EvalResult(case_id="c2", passed=False, schema_valid=True, quality_checks={"has_claims": False}, output={}),
        ],
    )
    fake_cases = [
        EvalCase(id="c1", engine="gap"),
        EvalCase(id="c2", engine="synthesis"),
    ]

    with patch("maelstrom.services.eval_service.EvalRunner") as MockRunner, \
         patch("maelstrom.services.eval_service.load_case_from_file") as mock_load, \
         patch("maelstrom.services.eval_service.Path") as MockPath:
        instance = MockRunner.return_value
        instance.run_suite = AsyncMock(return_value=fake_suite)

        # Mock cases dir
        mock_dir = MagicMock()
        mock_dir.is_dir.return_value = True
        mock_fp1 = MagicMock()
        mock_fp1.__str__ = lambda self: "c1.json"
        mock_fp2 = MagicMock()
        mock_fp2.__str__ = lambda self: "c2.json"
        mock_dir.glob.return_value = [mock_fp1, mock_fp2]
        MockPath.return_value = mock_dir
        # sorted() needs comparable items
        mock_fp1.__lt__ = lambda self, other: True
        mock_fp2.__lt__ = lambda self, other: False

        mock_load.side_effect = fake_cases

        run = await eval_repo.create_eval_run(db, "regression")
        await eval_repo.update_eval_run(db, run["id"], "running")
        summary = await eval_service._run_regression(db, run["id"], None)

    assert summary["total"] == 2
    assert summary["passed"] == 1
    results = await eval_repo.list_case_results(db, run["id"])
    assert len(results) == 2


@pytest.mark.asyncio
async def test_replay_mode(db):
    """Insert a fake gap_run and verify offline evaluation."""
    now = datetime.now(timezone.utc).isoformat()
    result_data = {"ranked_gaps": [{"id": "g1"}], "claims": ["c1"], "review_report": "ok"}
    await db.execute(
        "INSERT INTO gap_runs (id, session_id, topic, status, result_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("run-1", "s1", "test", "completed", json.dumps(result_data), now),
    )
    await db.commit()

    run = await eval_repo.create_eval_run(db, "replay", target_run_id="run-1")
    await eval_repo.update_eval_run(db, run["id"], "running")
    summary = await eval_service._run_replay(db, run["id"], "run-1", None)

    assert summary["total"] == 1
    results = await eval_repo.list_case_results(db, run["id"])
    assert len(results) == 1
    assert results[0]["engine"] == "gap"


@pytest.mark.asyncio
async def test_runtime_metrics(db):
    """Insert trace_events and verify aggregation."""
    t0 = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(milliseconds=500)
    t2 = t0 + timedelta(milliseconds=1200)
    t3 = t0 + timedelta(milliseconds=1500)

    await trace_event_repo.create_trace_event(db, "r1", "s1", "gap", "step_start", "search")
    # Override timestamp for deterministic test
    await db.execute("UPDATE trace_events SET timestamp = ? WHERE node_name = 'search' AND event_type = 'step_start'", (t0.isoformat(),))

    await trace_event_repo.create_trace_event(db, "r1", "s1", "gap", "step_complete", "search")
    await db.execute("UPDATE trace_events SET timestamp = ? WHERE node_name = 'search' AND event_type = 'step_complete'", (t1.isoformat(),))

    await trace_event_repo.create_trace_event(db, "r1", "s1", "gap", "error", None)
    await db.execute("UPDATE trace_events SET timestamp = ? WHERE event_type = 'error'", (t2.isoformat(),))

    await trace_event_repo.create_trace_event(db, "r1", "s1", "gap", "tool_call", None)
    await db.execute("UPDATE trace_events SET timestamp = ? WHERE event_type = 'tool_call'", (t3.isoformat(),))

    await db.commit()

    metrics = await eval_service.compute_runtime_metrics(db, run_id="r1")
    assert len(metrics) == 1
    m = metrics[0]
    assert m["engine"] == "gap"
    assert m["step_count"] == 1
    assert "search" in m["step_durations"]
    assert m["step_durations"]["search"] == pytest.approx(500.0, abs=50)
    assert m["error_count"] == 1
    assert m["tool_call_count"] == 1
    assert m["total_duration_ms"] is not None
    assert m["total_duration_ms"] == pytest.approx(1500.0, abs=50)
