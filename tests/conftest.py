import pytest
import aiosqlite

from maelstrom.db.migrations import run_migrations


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def test_db():
    """In-memory SQLite database with all migrations applied."""
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await run_migrations(db)
    yield db
    await db.close()


@pytest.fixture
def mock_llm():
    """Reusable mock for call_llm. Returns a factory that creates AsyncMock with side_effect."""
    from unittest.mock import AsyncMock

    def _make_mock(responses: list[str]):
        idx = {"i": 0}

        async def _side_effect(prompt, profile, **kwargs):
            i = idx["i"]
            idx["i"] += 1
            return responses[i] if i < len(responses) else "{}"

        mock = AsyncMock(side_effect=_side_effect)
        return mock

    return _make_mock
