"""P1-14: Gap → QA Chat link – share-to-qa endpoint tests."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, patch

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
    resp = await client.post("/api/sessions", json={"title": "ShareTest"})
    return resp.json()["id"]


@pytest.fixture
async def configured_client(client):
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


def _mock_execute_run(papers=None):
    """Patch _execute_run to simulate a completed run."""
    if papers is None:
        papers = [
            {"paper_id": "p1", "title": "Paper 1", "source": "arxiv", "pdf_url": "https://example.com/p1.pdf"},
            {"paper_id": "p2", "title": "Paper 2", "source": "s2"},
        ]

    async def _fake_execute(run_id, session_id, topic, profile=None):
        from maelstrom.db import gap_run_repo, run_paper_repo
        db = await database.get_db()
        await gap_run_repo.update_gap_run_status(db, run_id, "running")
        gap_service._run_state[run_id]["current_step"] = "paper_retrieval"

        paper_jsons = [json.dumps(p) for p in papers]
        await run_paper_repo.bulk_create_for_run(db, run_id, paper_jsons)

        result = {
            "ranked_gaps": [],
            "topic_candidates": [],
            "papers": papers,
            "coverage_matrix": {"cells": {}, "summary": {"tasks": 0}},
            "search_result": {"total_papers": len(papers), "source_statuses": []},
        }
        await gap_run_repo.update_gap_run_result(db, run_id, json.dumps(result))
        await gap_run_repo.update_gap_run_status(db, run_id, "completed")
        gap_service._run_state[run_id]["current_step"] = "completed"
        gap_service._run_state[run_id]["result"] = result

    return patch("maelstrom.services.gap_service._execute_run", side_effect=_fake_execute)


@pytest.mark.asyncio
async def test_share_to_qa_success(configured_client, session_id):
    """Share papers from completed run calls share_papers_to_qa."""
    with _mock_execute_run():
        resp = await configured_client.post("/api/gap/run", json={
            "topic": "test", "session_id": session_id,
        })
        run_id = resp.json()["run_id"]
        await _wait_run(run_id)

    mock_share = AsyncMock(return_value={"shared": 1, "failed": 0, "skipped": 1})
    with patch("maelstrom.api.gap.share_papers_to_qa", mock_share):
        resp = await configured_client.post(
            f"/api/gap/run/{run_id}/share-to-qa",
            json={"session_id": session_id},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["shared"] == 1
    assert data["skipped"] == 1
    # Verify called with correct args
    mock_share.assert_called_once()
    call_args = mock_share.call_args
    assert call_args[0][0] == session_id
    assert len(call_args[0][1]) == 2  # both papers passed


@pytest.mark.asyncio
async def test_share_to_qa_missing_session_id(configured_client, session_id):
    """Returns 400 when session_id not provided."""
    with _mock_execute_run():
        resp = await configured_client.post("/api/gap/run", json={
            "topic": "test", "session_id": session_id,
        })
        run_id = resp.json()["run_id"]
        await _wait_run(run_id)

    resp = await configured_client.post(
        f"/api/gap/run/{run_id}/share-to-qa", json={},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_share_to_qa_run_not_found(configured_client, session_id):
    """Returns 404 for nonexistent run."""
    resp = await configured_client.post(
        "/api/gap/run/nonexistent/share-to-qa",
        json={"session_id": session_id},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_share_to_qa_run_not_done(configured_client, session_id):
    """Returns 409 when run is still in progress."""
    from maelstrom.db import gap_run_repo
    db = await database.get_db()
    run = await gap_run_repo.create_gap_run(db, session_id, "test")
    run_id = run["id"]
    gap_service._run_state[run_id] = {"current_step": "running", "result": None, "error": None}

    resp = await configured_client.post(
        f"/api/gap/run/{run_id}/share-to-qa",
        json={"session_id": session_id},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_share_to_qa_no_papers(configured_client, session_id):
    """Returns zeros when run has no papers."""
    with _mock_execute_run(papers=[]):
        resp = await configured_client.post("/api/gap/run", json={
            "topic": "test", "session_id": session_id,
        })
        run_id = resp.json()["run_id"]
        await _wait_run(run_id)

    resp = await configured_client.post(
        f"/api/gap/run/{run_id}/share-to-qa",
        json={"session_id": session_id},
    )
    assert resp.status_code == 200
    assert resp.json() == {"shared": 0, "failed": 0, "skipped": 0}
