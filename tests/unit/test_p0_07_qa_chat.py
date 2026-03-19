import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from maelstrom.db import database
from maelstrom.db.migrations import run_migrations
from maelstrom.services import chat_service, llm_config_service
from maelstrom.schemas.llm_config import LLMProfile, MaelstromConfig


@pytest.fixture(autouse=True)
async def use_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.set_db_path(tmp.name)
    db = await database.get_db()
    await run_migrations(db)
    chat_service._qa_tasks.clear()
    llm_config_service._config = MaelstromConfig(
        profiles={"default": LLMProfile(name="Default", model="gpt-4o", api_key="sk-test")},
        active_profile="default",
    )
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
    resp = await client.post("/api/sessions", json={"title": "ChatTest"})
    return resp.json()["id"]


async def _wait_task(msg_id: str, timeout: float = 5.0):
    for _ in range(int(timeout / 0.1)):
        task = chat_service.get_task(msg_id)
        if task and task["status"] in ("done", "error"):
            return task
        await asyncio.sleep(0.1)
    return chat_service.get_task(msg_id)


@pytest.mark.asyncio
async def test_ask_returns_msg_id(client, session_id):
    with patch("maelstrom.services.chat_service._paperqa_service") as mock_svc:
        mock_svc.build_settings.return_value = object()
        mock_svc.ask = AsyncMock(return_value={"answer": "test", "citations": []})
        resp = await client.post("/api/chat/ask", json={
            "session_id": session_id, "question": "What is X?"
        })
        assert resp.status_code == 202
        assert "msg_id" in resp.json()
        await _wait_task(resp.json()["msg_id"])


@pytest.mark.asyncio
async def test_ask_invalid_session(client):
    resp = await client.post("/api/chat/ask", json={
        "session_id": "nonexistent", "question": "What?"
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_chat_message_persisted(client, session_id):
    with patch("maelstrom.services.chat_service._paperqa_service") as mock_svc:
        mock_svc.build_settings.return_value = object()
        mock_svc.ask = AsyncMock(return_value={"answer": "The answer", "citations": []})
        resp = await client.post("/api/chat/ask", json={
            "session_id": session_id, "question": "What is Y?"
        })
        msg_id = resp.json()["msg_id"]
        await _wait_task(msg_id)

    from maelstrom.db import chat_repo
    db = await database.get_db()
    msgs = await chat_repo.list_messages_by_session(db, session_id)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "The answer"


@pytest.mark.asyncio
async def test_sse_stream_events(client, session_id):
    with patch("maelstrom.services.chat_service._paperqa_service") as mock_svc:
        mock_svc.build_settings.return_value = object()
        mock_svc.ask = AsyncMock(return_value={"answer": "hello world", "citations": []})
        resp = await client.post("/api/chat/ask", json={
            "session_id": session_id, "question": "Test?"
        })
        msg_id = resp.json()["msg_id"]
        await _wait_task(msg_id)

    events = []
    async for event in chat_service.stream_answer(msg_id):
        events.append(event)

    token_events = [e for e in events if e["event"] == "chat_token"]
    done_events = [e for e in events if e["event"] == "chat_done"]
    assert len(token_events) >= 1
    assert len(done_events) == 1
    done_data = json.loads(done_events[0]["data"])
    assert done_data["answer"] == "hello world"


@pytest.mark.asyncio
async def test_sse_error_event(client, session_id):
    from maelstrom.services.paperqa_service import PaperQAError

    with patch("maelstrom.services.chat_service._paperqa_service") as mock_svc:
        mock_svc.build_settings.return_value = object()
        mock_svc.ask = AsyncMock(side_effect=PaperQAError("LLM failed"))
        resp = await client.post("/api/chat/ask", json={
            "session_id": session_id, "question": "Fail?"
        })
        msg_id = resp.json()["msg_id"]
        await _wait_task(msg_id)

    events = []
    async for event in chat_service.stream_answer(msg_id):
        events.append(event)

    error_events = [e for e in events if e["event"] == "error"]
    assert len(error_events) == 1
    assert "LLM failed" in json.loads(error_events[0]["data"])["message"]
