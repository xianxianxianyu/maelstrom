"""P1-11: Gap Engine API endpoint tests."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from maelstrom.db import database
from maelstrom.db.migrations import run_migrations
from maelstrom.services import gap_service, llm_config_service


@pytest.fixture(autouse=True)
async def use_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.set_db_path(tmp.name)
    db = await database.get_db()
    await run_migrations(db)
    gap_service._run_state.clear()
    from maelstrom.schemas.llm_config import MaelstromConfig
    llm_config_service._config = MaelstromConfig()
    yield
    await database.close_db()
    os.unlink(tmp.name)


@pytest.fixture
async def client():
    from maelstrom.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def session_id(client):
    resp = await client.post("/api/sessions", json={"title": "GapTest"})
    return resp.json()["id"]


@pytest.fixture
async def configured_client(client):
    """Client with LLM configured."""
    from maelstrom.schemas.llm_config import LLMProfile, MaelstromConfig
    llm_config_service._config = MaelstromConfig(
        profiles={"default": LLMProfile(name="Default", model="gpt-4o", api_key="sk-test")},
        active_profile="default",
    )
    return client
async def _wait_run(run_id: str, timeout: float = 5.0):
    for _ in range(int(timeout / 0.1)):
        status = await gap_service.get_status(run_id)
        if status and status["status"] in ("completed", "failed"):
            return status
        await asyncio.sleep(0.1)
    return await gap_service.get_status(run_id)


def _mock_execute_run():
    """Patch _execute_run to simulate a completed run without real LLM/adapters."""
    async def _fake_execute(run_id, session_id, topic, profile=None):
        from maelstrom.db import gap_run_repo, run_paper_repo
        db = await database.get_db()
        await gap_run_repo.update_gap_run_status(db, run_id, "running")
        gap_service._run_state[run_id]["current_step"] = "paper_retrieval"

        papers = [{"paper_id": "p1", "title": "Paper 1", "source": "mock"}]
        paper_jsons = [json.dumps(p) for p in papers]
        await run_paper_repo.bulk_create_for_run(db, run_id, paper_jsons)

        result = {
            "ranked_gaps": [{"title": "Gap A", "scores": {"novelty": 0.8, "feasibility": 0.7, "impact": 0.6}}],
            "topic_candidates": [{"title": "Topic A", "related_gap_ids": ["Gap A"]}],
            "papers": papers,
            "coverage_matrix": {"cells": {"T|M|D|Met": ["p1"]}, "summary": {"tasks": 1}},
            "search_result": {"total_papers": 1, "source_statuses": []},
        }
        await gap_run_repo.update_gap_run_result(db, run_id, json.dumps(result))
        await gap_run_repo.update_gap_run_status(db, run_id, "completed")
        gap_service._run_state[run_id]["current_step"] = "completed"
        gap_service._run_state[run_id]["result"] = result

    return patch("maelstrom.services.gap_service._execute_run", side_effect=_fake_execute)


@pytest.mark.asyncio
async def test_start_gap_run(configured_client, session_id):
    with _mock_execute_run():
        resp = await configured_client.post("/api/gap/run", json={
            "topic": "transformer efficiency", "session_id": session_id,
        })
    assert resp.status_code == 202
    assert "run_id" in resp.json()


@pytest.mark.asyncio
async def test_start_invalid_session(configured_client):
    resp = await configured_client.post("/api/gap/run", json={
        "topic": "test topic", "session_id": "nonexistent",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_start_no_llm_config(client, session_id):
    resp = await client.post("/api/gap/run", json={
        "topic": "test topic", "session_id": session_id,
    })
    assert resp.status_code == 400
    assert "profile" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_status_completed(configured_client, session_id):
    with _mock_execute_run():
        resp = await configured_client.post("/api/gap/run", json={
            "topic": "transformer efficiency", "session_id": session_id,
        })
        run_id = resp.json()["run_id"]
        await _wait_run(run_id)

    resp = await configured_client.get(f"/api/gap/run/{run_id}/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_get_result_completed(configured_client, session_id):
    with _mock_execute_run():
        resp = await configured_client.post("/api/gap/run", json={
            "topic": "transformer efficiency", "session_id": session_id,
        })
        run_id = resp.json()["run_id"]
        await _wait_run(run_id)

    resp = await configured_client.get(f"/api/gap/run/{run_id}/result")
    assert resp.status_code == 200
    data = resp.json()
    assert "ranked_gaps" in data
    assert "topic_candidates" in data
    assert "papers" in data
    assert "coverage_matrix" in data
    assert "search_result" in data


@pytest.mark.asyncio
async def test_get_result_not_ready(configured_client, session_id):
    # Create a run but don't let it complete
    from maelstrom.db import gap_run_repo
    db = await database.get_db()
    run = await gap_run_repo.create_gap_run(db, session_id, "test")
    run_id = run["id"]
    gap_service._run_state[run_id] = {"current_step": "running", "result": None, "error": None}

    resp = await configured_client.get(f"/api/gap/run/{run_id}/result")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_papers_endpoint(configured_client, session_id):
    with _mock_execute_run():
        resp = await configured_client.post("/api/gap/run", json={
            "topic": "test", "session_id": session_id,
        })
        run_id = resp.json()["run_id"]
        await _wait_run(run_id)

    resp = await configured_client.get(f"/api/gap/run/{run_id}/papers")
    assert resp.status_code == 200
    data = resp.json()
    assert "papers" in data
    assert len(data["papers"]) == 1
    assert data["papers"][0]["paper_id"] == "p1"


@pytest.mark.asyncio
async def test_get_matrix_endpoint(configured_client, session_id):
    with _mock_execute_run():
        resp = await configured_client.post("/api/gap/run", json={
            "topic": "test", "session_id": session_id,
        })
        run_id = resp.json()["run_id"]
        await _wait_run(run_id)

    resp = await configured_client.get(f"/api/gap/run/{run_id}/matrix")
    assert resp.status_code == 200
    data = resp.json()
    assert "cells" in data
    assert "summary" in data


@pytest.mark.asyncio
async def test_run_persisted(configured_client, session_id):
    with _mock_execute_run():
        resp = await configured_client.post("/api/gap/run", json={
            "topic": "test", "session_id": session_id,
        })
        run_id = resp.json()["run_id"]
        await _wait_run(run_id)

    from maelstrom.db import gap_run_repo
    db = await database.get_db()
    run = await gap_run_repo.get_gap_run(db, run_id)
    assert run is not None
    assert run["status"] == "completed"


@pytest.mark.asyncio
async def test_papers_persisted(configured_client, session_id):
    with _mock_execute_run():
        resp = await configured_client.post("/api/gap/run", json={
            "topic": "test", "session_id": session_id,
        })
        run_id = resp.json()["run_id"]
        await _wait_run(run_id)

    from maelstrom.db import run_paper_repo
    db = await database.get_db()
    rows = await run_paper_repo.list_by_run(db, run_id)
    assert len(rows) == 1
