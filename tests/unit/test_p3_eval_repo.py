"""P3 Eval Repo — unit tests for eval_repo CRUD operations."""
from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite
import pytest

from maelstrom.db.migrations import run_migrations
from maelstrom.db import eval_repo


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await run_migrations(conn)
    yield conn
    await conn.close()


@pytest.mark.asyncio
async def test_create_and_get_eval_run(db):
    run = await eval_repo.create_eval_run(db, "regression", engine_filter="gap")
    assert run["mode"] == "regression"
    assert run["status"] == "pending"
    assert run["engine_filter"] == "gap"

    fetched = await eval_repo.get_eval_run(db, run["id"])
    assert fetched is not None
    assert fetched["id"] == run["id"]
    assert fetched["mode"] == "regression"


@pytest.mark.asyncio
async def test_update_eval_run_status(db):
    run = await eval_repo.create_eval_run(db, "replay", target_run_id="r1")
    assert run["status"] == "pending"

    updated = await eval_repo.update_eval_run(db, run["id"], "running")
    assert updated["status"] == "running"
    assert updated["completed_at"] is None

    updated2 = await eval_repo.update_eval_run(
        db, run["id"], "completed", '{"total": 1, "passed": 1}'
    )
    assert updated2["status"] == "completed"
    assert updated2["completed_at"] is not None


@pytest.mark.asyncio
async def test_list_eval_runs_pagination(db):
    for i in range(5):
        await eval_repo.create_eval_run(db, "regression")

    items, total = await eval_repo.list_eval_runs(db, offset=0, limit=3)
    assert total == 5
    assert len(items) == 3

    items2, total2 = await eval_repo.list_eval_runs(db, offset=3, limit=3)
    assert total2 == 5
    assert len(items2) == 2


@pytest.mark.asyncio
async def test_create_and_list_case_results(db):
    run = await eval_repo.create_eval_run(db, "regression")
    cr1 = await eval_repo.create_case_result(
        db, run["id"], "case-1", "gap", True, True,
        '{"min_gaps": true}', '{"gaps": [1]}',
    )
    cr2 = await eval_repo.create_case_result(
        db, run["id"], "case-2", "synthesis", False, True,
        '{"has_claims": false}', '{}', error="quality check failed",
    )

    results = await eval_repo.list_case_results(db, run["id"])
    assert len(results) == 2
    assert results[0]["case_id"] == "case-1"
    assert results[0]["passed"] == 1
    assert results[1]["case_id"] == "case-2"
    assert results[1]["passed"] == 0
    assert results[1]["error"] == "quality check failed"
