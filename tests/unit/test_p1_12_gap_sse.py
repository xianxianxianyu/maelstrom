"""P1-12: Gap Engine SSE progress tests."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from unittest.mock import patch

import pytest

from maelstrom.db import database
from maelstrom.db.migrations import run_migrations
from maelstrom.services import gap_service, llm_config_service
from maelstrom.services.event_bus import EventBus, set_event_bus, get_event_bus


@pytest.fixture(autouse=True)
async def use_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.set_db_path(tmp.name)
    db = await database.get_db()
    await run_migrations(db)
    gap_service._run_state.clear()
    set_event_bus(EventBus())
    from maelstrom.schemas.llm_config import MaelstromConfig
    llm_config_service._config = MaelstromConfig()
    yield
    await database.close_db()
    os.unlink(tmp.name)


async def _setup_session():
    from maelstrom.db import session_repo
    db = await database.get_db()
    s = await session_repo.create_session(db, "SSETest")
    return s["id"]


async def _fake_execute(run_id, session_id, topic):
    """Simulate a full run emitting all SSE events."""
    from maelstrom.db import gap_run_repo
    db = await database.get_db()
    await gap_run_repo.update_gap_run_status(db, run_id, "running")
    bus = get_event_bus()

    steps = ["topic_intake", "query_expansion", "paper_retrieval",
             "normalize_dedup", "coverage_matrix", "gap_hypothesis",
             "gap_critic", "ranking_packaging"]

    papers = [{"paper_id": "p1", "title": "Paper 1", "source": "mock"}]
    matrix = {"cells": {"T|M|D|Met": ["p1"]}, "summary": {"tasks": 1, "methods": 1, "datasets": 1, "metrics": 1}}
    gaps = [{"title": "Gap A", "summary": "s", "gap_type": "method", "evidence_refs": ["p1"], "confidence": 0.8}]

    for idx, step in enumerate(steps):
        gap_service._run_state[run_id]["current_step"] = step
        await bus.emit(run_id, "step_start", {"step": step, "index": idx}, session_id=session_id, engine="gap")
        await asyncio.sleep(0)
        await bus.emit(run_id, "step_complete", {"step": step, "summary": f"{step} done"}, session_id=session_id, engine="gap")

        if step == "normalize_dedup":
            await bus.emit(run_id, "papers_found", {"count": 1, "papers": papers, "sources": []}, session_id=session_id, engine="gap")
        elif step == "coverage_matrix":
            await bus.emit(run_id, "matrix_ready", {"coverage_matrix": matrix, "summary": matrix["summary"]}, session_id=session_id, engine="gap")
        elif step == "gap_hypothesis":
            for g in gaps:
                await bus.emit(run_id, "gap_found", {"gap": g}, session_id=session_id, engine="gap")

    result = {"gaps": gaps, "candidates": [{"title": "Topic A"}]}
    await bus.emit(run_id, "result", result, session_id=session_id, engine="gap")

    full_result = {"ranked_gaps": gaps, "topic_candidates": [{"title": "Topic A"}],
                   "papers": papers, "coverage_matrix": matrix, "search_result": {}}
    await gap_run_repo.update_gap_run_result(db, run_id, json.dumps(full_result))
    await gap_run_repo.update_gap_run_status(db, run_id, "completed")
    gap_service._run_state[run_id]["current_step"] = "completed"
    await bus.emit(run_id, "__done__", {}, session_id=session_id, engine="gap")


async def _collect_events(q: asyncio.Queue, timeout: float = 3.0) -> list[dict]:
    """Collect all events from a queue until __done__."""
    events = []
    try:
        while True:
            event = await asyncio.wait_for(q.get(), timeout=timeout)
            if event["event"] == "__done__":
                break
            events.append(event)
    except asyncio.TimeoutError:
        pass
    return events


async def _start_and_collect(sid: str, topic: str = "test topic") -> list[dict]:
    """Subscribe, start run, collect events."""
    with patch("maelstrom.services.gap_service._execute_run", side_effect=_fake_execute):
        from maelstrom.db import gap_run_repo
        db = await database.get_db()
        run = await gap_run_repo.create_gap_run(db, sid, topic)
        run_id = run["id"]
        gap_service._run_state[run_id] = {"current_step": "pending", "result": None, "error": None}

        q = gap_service.subscribe(run_id)
        task = asyncio.create_task(_fake_execute(run_id, sid, topic))
        events = await _collect_events(q)
        gap_service.unsubscribe(run_id, q)
        await task
    return events, run_id


@pytest.mark.asyncio
async def test_sse_connection():
    sid = await _setup_session()
    events, _ = await _start_and_collect(sid)
    assert len(events) > 0


@pytest.mark.asyncio
async def test_sse_step_events():
    sid = await _setup_session()
    events, _ = await _start_and_collect(sid)
    starts = [e for e in events if e["event"] == "step_start"]
    completes = [e for e in events if e["event"] == "step_complete"]
    assert len(starts) == 8
    assert len(completes) == 8


@pytest.mark.asyncio
async def test_sse_papers_found():
    sid = await _setup_session()
    events, _ = await _start_and_collect(sid)
    pf = [e for e in events if e["event"] == "papers_found"]
    assert len(pf) == 1
    data = json.loads(pf[0]["data"])
    assert data["count"] == 1
    assert len(data["papers"]) == 1
    assert data["papers"][0]["paper_id"] == "p1"


@pytest.mark.asyncio
async def test_sse_matrix_ready():
    sid = await _setup_session()
    events, _ = await _start_and_collect(sid)
    mr = [e for e in events if e["event"] == "matrix_ready"]
    assert len(mr) == 1
    data = json.loads(mr[0]["data"])
    assert "coverage_matrix" in data
    assert "summary" in data


@pytest.mark.asyncio
async def test_sse_gap_found():
    sid = await _setup_session()
    events, _ = await _start_and_collect(sid)
    gf = [e for e in events if e["event"] == "gap_found"]
    assert len(gf) >= 1
    data = json.loads(gf[0]["data"])
    assert "gap" in data
    assert data["gap"]["title"] == "Gap A"


@pytest.mark.asyncio
async def test_sse_result():
    sid = await _setup_session()
    events, _ = await _start_and_collect(sid)
    res = [e for e in events if e["event"] == "result"]
    assert len(res) == 1
    data = json.loads(res[0]["data"])
    assert "gaps" in data
    assert "candidates" in data


@pytest.mark.asyncio
async def test_sse_error():
    sid = await _setup_session()
    bus = get_event_bus()

    async def _fail_execute(run_id, session_id, topic):
        from maelstrom.db import gap_run_repo
        db = await database.get_db()
        await gap_run_repo.update_gap_run_status(db, run_id, "failed")
        gap_service._run_state[run_id]["current_step"] = "failed"
        await bus.emit(run_id, "error", {"message": "boom", "step": "topic_intake"}, session_id=session_id, engine="gap")
        await bus.emit(run_id, "__done__", {}, session_id=session_id, engine="gap")

    from maelstrom.db import gap_run_repo
    db = await database.get_db()
    run = await gap_run_repo.create_gap_run(db, sid, "fail topic")
    run_id = run["id"]
    gap_service._run_state[run_id] = {"current_step": "pending", "result": None, "error": None}
    q = gap_service.subscribe(run_id)
    task = asyncio.create_task(_fail_execute(run_id, sid, "fail topic"))
    events = await _collect_events(q)
    gap_service.unsubscribe(run_id, q)
    await task

    errs = [e for e in events if e["event"] == "error"]
    assert len(errs) == 1
    assert "boom" in json.loads(errs[0]["data"])["message"]


@pytest.mark.asyncio
async def test_sse_event_order():
    sid = await _setup_session()
    events, _ = await _start_and_collect(sid)
    types = [e["event"] for e in events]
    assert types.index("papers_found") < types.index("matrix_ready")
    assert types.index("matrix_ready") < types.index("gap_found")
    assert types.index("gap_found") < types.index("result")


@pytest.mark.asyncio
async def test_sse_invalid_run_id():
    from httpx import ASGITransport, AsyncClient
    from maelstrom.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/gap/run/nonexistent/stream")
    assert resp.status_code == 404
