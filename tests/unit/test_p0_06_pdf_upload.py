import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from maelstrom.db import database
from maelstrom.db.migrations import run_migrations
from maelstrom.services import llm_config_service
from maelstrom.schemas.llm_config import LLMProfile, MaelstromConfig


@pytest.fixture(autouse=True)
async def use_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.set_db_path(tmp.name)
    db = await database.get_db()
    await run_migrations(db)
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
    resp = await client.post("/api/sessions", json={"title": "DocTest"})
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_upload_pdf(client, session_id):
    pdf_bytes = b"%PDF-1.4 fake pdf content"
    with patch("maelstrom.services.doc_service._paperqa_service") as mock_svc:
        mock_svc.build_settings.return_value = object()
        mock_svc.index_document = AsyncMock(return_value="/fake/path.pdf")
        resp = await client.post(
            "/api/chat/docs/upload",
            data={"session_id": session_id},
            files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["filename"] == "test.pdf"
    assert "doc_id" in data
    assert "indexed_at" in data


@pytest.mark.asyncio
async def test_upload_non_pdf(client, session_id):
    resp = await client.post(
        "/api/chat/docs/upload",
        data={"session_id": session_id},
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_upload_too_large(client, session_id):
    big = b"x" * (51 * 1024 * 1024)
    resp = await client.post(
        "/api/chat/docs/upload",
        data={"session_id": session_id},
        files={"file": ("big.pdf", big, "application/pdf")},
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_list_docs(client, session_id):
    pdf_bytes = b"%PDF-1.4 fake"
    with patch("maelstrom.services.doc_service._paperqa_service") as mock_svc:
        mock_svc.build_settings.return_value = object()
        mock_svc.index_document = AsyncMock(return_value="/fake/a.pdf")
        await client.post(
            "/api/chat/docs/upload",
            data={"session_id": session_id},
            files={"file": ("a.pdf", pdf_bytes, "application/pdf")},
        )
        mock_svc.index_document = AsyncMock(return_value="/fake/b.pdf")
        await client.post(
            "/api/chat/docs/upload",
            data={"session_id": session_id},
            files={"file": ("b.pdf", pdf_bytes, "application/pdf")},
        )
    resp = await client.get(f"/api/chat/docs?session_id={session_id}")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_delete_doc(client, session_id):
    pdf_bytes = b"%PDF-1.4 fake"
    with patch("maelstrom.services.doc_service._paperqa_service") as mock_svc:
        mock_svc.build_settings.return_value = object()
        mock_svc.index_document = AsyncMock(return_value="/fake/del.pdf")
        r = await client.post(
            "/api/chat/docs/upload",
            data={"session_id": session_id},
            files={"file": ("del.pdf", pdf_bytes, "application/pdf")},
        )
    doc_id = r.json()["doc_id"]
    resp = await client.delete(f"/api/chat/docs/{doc_id}")
    assert resp.status_code == 204

    docs = await client.get(f"/api/chat/docs?session_id={session_id}")
    assert len(docs.json()) == 0


@pytest.mark.asyncio
async def test_upload_invalid_session(client):
    resp = await client.post(
        "/api/chat/docs/upload",
        data={"session_id": "nonexistent"},
        files={"file": ("test.pdf", b"%PDF", "application/pdf")},
    )
    assert resp.status_code == 404
