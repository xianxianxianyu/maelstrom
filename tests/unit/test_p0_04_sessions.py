import os
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

from maelstrom.db import database


@pytest.fixture(autouse=True)
async def use_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.set_db_path(tmp.name)
    db = await database.get_db()
    from maelstrom.db.migrations import run_migrations
    await run_migrations(db)
    yield
    await database.close_db()
    os.unlink(tmp.name)


@pytest.fixture
async def client():
    from maelstrom.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_create_session(client):
    resp = await client.post("/api/sessions", json={"title": "My Session"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "My Session"
    assert data["status"] == "active"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_session_with_title(client):
    resp = await client.post("/api/sessions", json={"title": "Custom Title"})
    assert resp.status_code == 201
    assert resp.json()["title"] == "Custom Title"


@pytest.mark.asyncio
async def test_list_sessions(client):
    for i in range(3):
        await client.post("/api/sessions", json={"title": f"S{i}"})
    resp = await client.get("/api/sessions")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


@pytest.mark.asyncio
async def test_get_session(client):
    r = await client.post("/api/sessions", json={"title": "Test"})
    sid = r.json()["id"]
    resp = await client.get(f"/api/sessions/{sid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == sid


@pytest.mark.asyncio
async def test_get_session_not_found(client):
    resp = await client.get("/api/sessions/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_session(client):
    r = await client.post("/api/sessions", json={"title": "Del"})
    sid = r.json()["id"]
    resp = await client.delete(f"/api/sessions/{sid}")
    assert resp.status_code == 204
    resp2 = await client.get(f"/api/sessions/{sid}")
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_delete_cascade(client):
    r = await client.post("/api/sessions", json={"title": "Cascade"})
    sid = r.json()["id"]
    # Add related data directly via db
    db = await database.get_db()
    from maelstrom.db import artifact_repo, chat_repo, gap_run_repo
    await artifact_repo.create_artifact(db, sid, "gap")
    await chat_repo.create_chat_message(db, sid, "user", "hello")
    await gap_run_repo.create_gap_run(db, sid, "topic")

    resp = await client.delete(f"/api/sessions/{sid}")
    assert resp.status_code == 204

    # Verify cascade
    assert await artifact_repo.list_artifacts_by_session(db, sid) == []
    assert await chat_repo.list_messages_by_session(db, sid) == []
