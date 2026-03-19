import asyncio
import json
import os
import tempfile

import aiosqlite
import pytest

from maelstrom.db import (
    artifact_repo,
    chat_repo,
    gap_run_repo,
    migrations,
    run_paper_repo,
    session_repo,
)


@pytest.fixture
async def db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = await aiosqlite.connect(tmp.name)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    await migrations.run_migrations(conn)
    yield conn
    await conn.close()
    os.unlink(tmp.name)


@pytest.mark.asyncio
async def test_database_init(db):
    cur = await db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {r["name"] for r in await cur.fetchall()}
    for t in ("sessions", "artifacts", "chat_messages", "gap_runs", "run_papers"):
        assert t in tables, f"missing table {t}"


@pytest.mark.asyncio
async def test_wal_mode(db):
    cur = await db.execute("PRAGMA journal_mode")
    row = await cur.fetchone()
    assert row[0] == "wal"


@pytest.mark.asyncio
async def test_session_crud(db):
    s = await session_repo.create_session(db, title="Test")
    assert s["title"] == "Test"
    assert s["status"] == "active"

    fetched = await session_repo.get_session(db, s["id"])
    assert fetched is not None
    assert fetched["title"] == "Test"

    updated = await session_repo.update_session(db, s["id"], title="Updated")
    assert updated["title"] == "Updated"

    deleted = await session_repo.delete_session(db, s["id"])
    assert deleted is True
    assert await session_repo.get_session(db, s["id"]) is None


@pytest.mark.asyncio
async def test_artifact_crud(db):
    s = await session_repo.create_session(db, title="S")
    a1 = await artifact_repo.create_artifact(db, s["id"], "gap", '{"x":1}')
    a2 = await artifact_repo.create_artifact(db, s["id"], "paper", '{"y":2}')

    fetched = await artifact_repo.get_artifact(db, a1["id"])
    assert fetched is not None
    assert fetched["type"] == "gap"

    by_session = await artifact_repo.list_artifacts_by_session(db, s["id"])
    assert len(by_session) == 2

    by_type = await artifact_repo.list_artifacts_by_type(db, s["id"], "gap")
    assert len(by_type) == 1
    assert by_type[0]["id"] == a1["id"]


@pytest.mark.asyncio
async def test_chat_message_crud(db):
    s = await session_repo.create_session(db)
    await chat_repo.create_chat_message(db, s["id"], "user", "Hello")
    await chat_repo.create_chat_message(db, s["id"], "assistant", "Hi there")

    msgs = await chat_repo.list_messages_by_session(db, s["id"])
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_gap_run_crud(db):
    s = await session_repo.create_session(db)
    run = await gap_run_repo.create_gap_run(db, s["id"], "test topic")
    assert run["status"] == "pending"

    await gap_run_repo.update_gap_run_status(db, run["id"], "running")
    fetched = await gap_run_repo.get_gap_run(db, run["id"])
    assert fetched["status"] == "running"

    await gap_run_repo.update_gap_run_result(db, run["id"], '{"gaps":[]}')
    await gap_run_repo.update_gap_run_status(db, run["id"], "completed")
    fetched = await gap_run_repo.get_gap_run(db, run["id"])
    assert fetched["status"] == "completed"
    assert fetched["completed_at"] is not None
    assert fetched["result_json"] == '{"gaps":[]}'


@pytest.mark.asyncio
async def test_cascade_delete(db):
    s = await session_repo.create_session(db)
    await artifact_repo.create_artifact(db, s["id"], "gap")
    await chat_repo.create_chat_message(db, s["id"], "user", "msg")
    run = await gap_run_repo.create_gap_run(db, s["id"], "topic")

    await session_repo.delete_session(db, s["id"])

    assert await artifact_repo.list_artifacts_by_session(db, s["id"]) == []
    assert await chat_repo.list_messages_by_session(db, s["id"]) == []
    assert await gap_run_repo.get_gap_run(db, run["id"]) is None


@pytest.mark.asyncio
async def test_run_paper_bulk_create(db):
    s = await session_repo.create_session(db)
    run = await gap_run_repo.create_gap_run(db, s["id"], "topic")
    papers = [json.dumps({"paper_id": f"p-{i}"}) for i in range(50)]
    count = await run_paper_repo.bulk_create_for_run(db, run["id"], papers)
    assert count == 50

    rows = await run_paper_repo.list_by_run(db, run["id"])
    assert len(rows) == 50


@pytest.mark.asyncio
async def test_run_paper_cascade_delete(db):
    s = await session_repo.create_session(db)
    run = await gap_run_repo.create_gap_run(db, s["id"], "topic")
    await run_paper_repo.bulk_create_for_run(db, run["id"], ['{"id":"p1"}'])

    # Delete gap_run → run_papers should cascade
    await db.execute("DELETE FROM gap_runs WHERE id = ?", (run["id"],))
    await db.commit()
    rows = await run_paper_repo.list_by_run(db, run["id"])
    assert rows == []


@pytest.mark.asyncio
async def test_concurrent_read_write(db):
    s = await session_repo.create_session(db)

    async def writer(i: int):
        await chat_repo.create_chat_message(db, s["id"], "user", f"msg-{i}")

    async def reader():
        return await chat_repo.list_messages_by_session(db, s["id"])

    await asyncio.gather(*[writer(i) for i in range(5)], reader(), reader())
    msgs = await chat_repo.list_messages_by_session(db, s["id"])
    assert len(msgs) == 5
