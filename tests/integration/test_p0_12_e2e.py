"""P0-12: Integration tests – end-to-end API flows with mocked paper-qa."""

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
    resp = await client.post("/api/sessions", json={"title": "IntegTest"})
    return resp.json()["id"]


async def _wait_task(msg_id: str, timeout: float = 5.0):
    for _ in range(int(timeout / 0.1)):
        task = chat_service.get_task(msg_id)
        if task and task["status"] in ("done", "error"):
            return task
        await asyncio.sleep(0.1)
    return chat_service.get_task(msg_id)
# --- Test 1: LLM config roundtrip ---

@pytest.mark.asyncio
async def test_e2e_llm_config_roundtrip(client):
    """POST profile → GET config → values match."""
    resp = await client.post("/api/config/profiles/test", json={
        "name": "Test",
        "protocol": "openai_chat",
        "model": "gpt-4o",
        "api_key": "sk-test-key",
        "temperature": 0.3,
    })
    assert resp.status_code == 200
    assert "test" in resp.json()["profiles"]

    get_resp = await client.get("/api/config")
    assert get_resp.status_code == 200
    data = get_resp.json()
    profile = data["profiles"]["test"]
    assert profile["protocol"] == "openai_chat"
    assert profile["model"] == "gpt-4o"
    assert profile["temperature"] == 0.3


# --- Test 2: Session lifecycle ---

@pytest.mark.asyncio
async def test_e2e_session_lifecycle(client):
    """Create → list → get → delete → verify gone."""
    # Create
    resp = await client.post("/api/sessions", json={"title": "Lifecycle"})
    assert resp.status_code == 201
    sid = resp.json()["id"]

    # List
    resp = await client.get("/api/sessions")
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.json()]
    assert sid in ids

    # Get
    resp = await client.get(f"/api/sessions/{sid}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Lifecycle"

    # Delete
    resp = await client.delete(f"/api/sessions/{sid}")
    assert resp.status_code == 204

    # Verify gone
    resp = await client.get(f"/api/sessions/{sid}")
    assert resp.status_code == 404
# --- Test 3: PDF upload + doc list + delete ---

@pytest.mark.asyncio
async def test_e2e_pdf_upload_and_list(client, session_id):
    """Upload PDF → list docs → delete doc → verify removed."""
    pdf_bytes = b"%PDF-1.4 fake content"

    with patch("maelstrom.services.doc_service._paperqa_service") as mock_svc:
        mock_svc.build_settings.return_value = object()
        mock_svc.index_document = AsyncMock(return_value="fake-doc-id")

        resp = await client.post(
            "/api/chat/docs/upload",
            files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
            data={"session_id": session_id},
        )
        assert resp.status_code == 201
        doc = resp.json()
        assert doc["filename"] == "test.pdf"
        doc_id = doc["doc_id"]

    # List
    resp = await client.get(f"/api/chat/docs?session_id={session_id}")
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) == 1
    assert docs[0]["doc_id"] == doc_id

    # Delete
    resp = await client.delete(f"/api/chat/docs/{doc_id}")
    assert resp.status_code == 204

    # Verify removed
    resp = await client.get(f"/api/chat/docs?session_id={session_id}")
    assert resp.json() == []


# --- Test 4: Upload non-PDF rejected ---

@pytest.mark.asyncio
async def test_e2e_upload_non_pdf_rejected(client, session_id):
    resp = await client.post(
        "/api/chat/docs/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        data={"session_id": session_id},
    )
    assert resp.status_code == 415
    assert "PDF" in resp.json()["detail"]
# --- Test 5: Full QA chat flow ---

@pytest.mark.asyncio
async def test_e2e_qa_chat_flow(client, session_id):
    """Config LLM → upload PDF → ask question → stream SSE → verify answer + citations."""
    # 1. Configure LLM
    await client.post("/api/config/profiles/default", json={
        "name": "Default", "protocol": "openai_chat", "model": "gpt-4o", "api_key": "sk-test",
    })

    # 2. Upload PDF
    with patch("maelstrom.services.doc_service._paperqa_service") as mock_doc:
        mock_doc.build_settings.return_value = object()
        mock_doc.index_document = AsyncMock(return_value="doc-1")
        await client.post(
            "/api/chat/docs/upload",
            files={"file": ("paper.pdf", b"%PDF-1.4 content", "application/pdf")},
            data={"session_id": session_id},
        )

    # 3. Ask question
    citations = [{"text": "ref text", "source": "paper.pdf", "page": 3}]
    with patch("maelstrom.services.chat_service._paperqa_service") as mock_qa:
        mock_qa.build_settings.return_value = object()
        mock_qa.ask = AsyncMock(return_value={
            "answer": "The answer is 42",
            "citations": citations,
        })
        resp = await client.post("/api/chat/ask", json={
            "session_id": session_id, "question": "What is the answer?",
        })
        assert resp.status_code == 202
        msg_id = resp.json()["msg_id"]
        await _wait_task(msg_id)

    # 4. Verify SSE stream
    events = []
    async for event in chat_service.stream_answer(msg_id):
        events.append(event)

    token_events = [e for e in events if e["event"] == "chat_token"]
    done_events = [e for e in events if e["event"] == "chat_done"]
    assert len(token_events) >= 1
    assert len(done_events) == 1
    done_data = json.loads(done_events[0]["data"])
    assert done_data["answer"] == "The answer is 42"
    assert len(done_data["citations"]) == 1

    # 5. Verify persisted in DB
    from maelstrom.db import chat_repo
    db = await database.get_db()
    msgs = await chat_repo.list_messages_by_session(db, session_id)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["content"] == "The answer is 42"
# --- Test 6: SSE format validation ---

@pytest.mark.asyncio
async def test_e2e_sse_format(client, session_id):
    """Verify SSE events have correct event/data structure."""
    with patch("maelstrom.services.chat_service._paperqa_service") as mock_svc:
        mock_svc.build_settings.return_value = object()
        mock_svc.ask = AsyncMock(return_value={"answer": "yes", "citations": []})
        resp = await client.post("/api/chat/ask", json={
            "session_id": session_id, "question": "Q?",
        })
        msg_id = resp.json()["msg_id"]
        await _wait_task(msg_id)

    async for event in chat_service.stream_answer(msg_id):
        assert "event" in event
        assert "data" in event
        assert event["event"] in ("chat_token", "chat_done", "error")
        # data must be valid JSON
        parsed = json.loads(event["data"])
        assert isinstance(parsed, dict)


# --- Test 7: Error on invalid API key (simulated) ---

@pytest.mark.asyncio
async def test_e2e_error_invalid_key(client, session_id):
    """Ask with a failing LLM → SSE error event."""
    from maelstrom.services.paperqa_service import PaperQAError

    with patch("maelstrom.services.chat_service._paperqa_service") as mock_svc:
        mock_svc.build_settings.return_value = object()
        mock_svc.ask = AsyncMock(side_effect=PaperQAError("Invalid API key"))
        resp = await client.post("/api/chat/ask", json={
            "session_id": session_id, "question": "Will fail?",
        })
        msg_id = resp.json()["msg_id"]
        await _wait_task(msg_id)

    events = []
    async for event in chat_service.stream_answer(msg_id):
        events.append(event)

    assert any(e["event"] == "error" for e in events)
    err_data = json.loads(events[0]["data"])
    assert "Invalid API key" in err_data["message"]


# --- Test 8: Session delete cascades data ---

@pytest.mark.asyncio
async def test_e2e_session_delete_cascades(client):
    """Create session → add chat + doc → delete session → verify cascade."""
    # Create session
    resp = await client.post("/api/sessions", json={"title": "Cascade"})
    sid = resp.json()["id"]

    # Add a chat message
    with patch("maelstrom.services.chat_service._paperqa_service") as mock_svc:
        mock_svc.build_settings.return_value = object()
        mock_svc.ask = AsyncMock(return_value={"answer": "ok", "citations": []})
        resp = await client.post("/api/chat/ask", json={
            "session_id": sid, "question": "Hi",
        })
        await _wait_task(resp.json()["msg_id"])

    # Upload a doc
    with patch("maelstrom.services.doc_service._paperqa_service") as mock_doc:
        mock_doc.build_settings.return_value = object()
        mock_doc.index_document = AsyncMock(return_value="d1")
        await client.post(
            "/api/chat/docs/upload",
            files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")},
            data={"session_id": sid},
        )

    # Delete session
    resp = await client.delete(f"/api/sessions/{sid}")
    assert resp.status_code == 204

    # Verify cascade: docs and messages gone
    from maelstrom.db import chat_repo, artifact_repo
    db = await database.get_db()
    msgs = await chat_repo.list_messages_by_session(db, sid)
    assert len(msgs) == 0
    arts = await artifact_repo.list_artifacts_by_type(db, sid, "indexed_doc")
    assert len(arts) == 0
