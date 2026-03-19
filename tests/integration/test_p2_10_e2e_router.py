"""P2-10: End-to-end integration tests for Phase Router."""
from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from maelstrom.db import database
from maelstrom.db.migrations import run_migrations
from maelstrom.services import gap_service, llm_config_service
from maelstrom.services.clarification_service import _clarification_counts
from maelstrom.services.evidence_memory import SqliteEvidenceMemory, set_evidence_memory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
async def use_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.set_db_path(tmp.name)
    db = await database.get_db()
    await run_migrations(db)
    gap_service._run_state.clear()
    from maelstrom.services.event_bus import EventBus, set_event_bus
    set_event_bus(EventBus())
    _clarification_counts.clear()
    # Set up EvidenceMemory with the test DB
    mem = SqliteEvidenceMemory(db=db)
    set_evidence_memory(mem)
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
    resp = await client.post("/api/sessions", json={"title": "P2 E2E Test"})
    return resp.json()["id"]


@pytest.fixture
async def configured_client(client):
    await client.post("/api/config/profiles/default", json={
        "name": "Default",
        "protocol": "openai_chat",
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-test",
        "model": "gpt-4o",
    })
    return client


# ---------------------------------------------------------------------------
# E2E-01: Router → QA Chat
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_router_qa_chat(configured_client, session_id):
    """QA intent → stream response pointing to chat SSE."""
    # Mock paper-qa to avoid real LLM call
    with patch("maelstrom.services.chat_service._run_qa", new_callable=AsyncMock):
        resp = await configured_client.post("/api/router/input", json={
            "session_id": session_id,
            "user_input": "这篇论文的方法是什么？",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["response_type"] == "stream"
    assert "/api/chat/" in data["stream_url"]
    assert data["intent"]["intent"] == "qa_chat"


# ---------------------------------------------------------------------------
# E2E-02: Router → Config redirect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_router_config(configured_client, session_id):
    """Config intent → redirect to /settings."""
    resp = await configured_client.post("/api/router/input", json={
        "session_id": session_id,
        "user_input": "切换到 Claude 模型",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["response_type"] == "redirect"
    assert data["redirect_path"] == "/settings"


# ---------------------------------------------------------------------------
# E2E-03: Router → Share redirect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_router_share(configured_client, session_id):
    """Share intent → redirect to /gap."""
    resp = await configured_client.post("/api/router/input", json={
        "session_id": session_id,
        "user_input": "把论文加到问答里",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["response_type"] == "redirect"
    assert data["redirect_path"] == "/gap"


# ---------------------------------------------------------------------------
# E2E-04: Router → Clarification → Resolve
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_clarification_flow(configured_client, session_id):
    """Ambiguous input → clarification → option select → resolved."""
    # Mock LLM classifier to return clarification_needed
    mock_llm_response = json.dumps({
        "intent": "clarification_needed",
        "confidence": 0.3,
        "reasoning": "unclear",
    })
    with patch("maelstrom.services.intent_classifier.call_llm", new_callable=AsyncMock, return_value=mock_llm_response), \
         patch("maelstrom.services.clarification_service.call_llm", new_callable=AsyncMock, side_effect=RuntimeError("no llm")):
        resp = await configured_client.post("/api/router/input", json={
            "session_id": session_id,
            "user_input": "transformer",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["response_type"] == "clarification"
    assert data["clarification"] is not None
    assert len(data["clarification"]["options"]) >= 2

    # Now resolve by selecting option 0
    request_id = data["clarification"]["request_id"]
    options = data["clarification"]["options"]

    with patch("maelstrom.services.chat_service._run_qa", new_callable=AsyncMock):
        resp2 = await configured_client.post("/api/chat/clarify", json={
            "session_id": session_id,
            "request_id": request_id,
            "option_index": 0,
        })
    assert resp2.status_code == 200
    data2 = resp2.json()
    # Should be routed to the selected intent (not clarification again)
    assert data2["response_type"] in ("stream", "redirect")


# ---------------------------------------------------------------------------
# E2E-05: Session phase tracking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_session_phase(configured_client, session_id):
    """Session starts with ideation phase."""
    resp = await configured_client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("current_phase", "ideation") == "ideation"


# ---------------------------------------------------------------------------
# E2E-06: Backward compatibility — direct /api/chat/ask
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_backward_compat_chat(configured_client, session_id):
    """Direct /api/chat/ask still works."""
    with patch("maelstrom.services.chat_service._run_qa", new_callable=AsyncMock):
        resp = await configured_client.post("/api/chat/ask", json={
            "session_id": session_id,
            "question": "What is attention?",
        })
    assert resp.status_code == 202
    assert "msg_id" in resp.json()


# ---------------------------------------------------------------------------
# E2E-07: Backward compatibility — direct /api/gap/run
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_backward_compat_gap(configured_client, session_id):
    """Direct /api/gap/run still works (returns 202 + run_id)."""
    # Mock the entire gap engine execution to avoid LLM calls
    with patch("maelstrom.services.gap_service._execute_run", new_callable=AsyncMock):
        resp = await configured_client.post("/api/gap/run", json={
            "topic": "NER efficiency",
            "session_id": session_id,
        })
    assert resp.status_code == 202
    assert "run_id" in resp.json()