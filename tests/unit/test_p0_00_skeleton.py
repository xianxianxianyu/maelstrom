import importlib
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from maelstrom.main import app


@pytest.mark.asyncio
async def test_health_check():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_project_structure():
    root = Path(__file__).resolve().parents[2]
    assert (root / "pyproject.toml").exists()
    assert (root / "src" / "maelstrom" / "__init__.py").exists()
    assert (root / "src" / "maelstrom" / "main.py").exists()
    for sub in ("schemas", "db", "api", "services", "adapters", "graph"):
        assert (root / "src" / "maelstrom" / sub / "__init__.py").exists(), f"missing {sub}/__init__.py"


def test_imports():
    mod = importlib.import_module("maelstrom")
    assert hasattr(mod, "__version__")
    assert mod.__version__ == "0.1.0"
