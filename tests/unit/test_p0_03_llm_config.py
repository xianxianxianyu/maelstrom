import pytest
from httpx import ASGITransport, AsyncClient

from maelstrom.main import app
from maelstrom.services import llm_config_service
from maelstrom.schemas.llm_config import MaelstromConfig


@pytest.fixture(autouse=True)
def reset_config():
    llm_config_service._config = MaelstromConfig()
    yield
    llm_config_service._config = MaelstromConfig()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_get_default_config(client):
    resp = await client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "profiles" in data
    assert "active_profile" in data


@pytest.mark.asyncio
async def test_create_and_update_profile(client):
    # Create a profile
    resp = await client.post("/api/config/profiles/test", json={
        "name": "Test",
        "protocol": "openai_chat",
        "model": "gpt-4o",
        "temperature": 0.7,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "test" in data["profiles"]

    # Update it
    resp2 = await client.put("/api/config/profiles/test", json={
        "name": "Test Updated",
        "protocol": "anthropic_messages",
        "model": "claude-sonnet-4-6",
        "temperature": 0.5,
    })
    assert resp2.status_code == 200
    assert resp2.json()["profiles"]["test"]["model"] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_update_invalid_temperature(client):
    resp = await client.post("/api/config/profiles/bad", json={
        "temperature": 5,
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_partial_config(client):
    # Create a profile first
    await client.post("/api/config/profiles/default", json={
        "name": "Default",
        "protocol": "openai_chat",
        "model": "gpt-4o",
        "temperature": 0.7,
    })
    # Update full config
    resp = await client.put("/api/config", json={
        "profiles": {"default": {"name": "Default", "protocol": "openai_chat", "model": "gpt-4o", "temperature": 1.0}},
        "active_profile": "default",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["profiles"]["default"]["temperature"] == 1.0
    assert data["profiles"]["default"]["protocol"] == "openai_chat"


@pytest.mark.asyncio
async def test_config_isolation(client):
    r1 = await client.get("/api/config")
    r2 = await client.get("/api/config")
    assert r1.json() == r2.json()
