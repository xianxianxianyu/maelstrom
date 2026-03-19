from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite


async def bulk_create_for_run(
    db: aiosqlite.Connection, run_id: str, paper_jsons: list[str]
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    rows = [(str(uuid.uuid4()), run_id, pj, now) for pj in paper_jsons]
    await db.executemany(
        "INSERT INTO run_papers (id, run_id, paper_json, created_at) VALUES (?, ?, ?, ?)",
        rows,
    )
    await db.commit()
    return len(rows)


async def list_by_run(db: aiosqlite.Connection, run_id: str) -> list[dict]:
    cur = await db.execute(
        "SELECT * FROM run_papers WHERE run_id = ? ORDER BY created_at", (run_id,)
    )
    return [dict(r) for r in await cur.fetchall()]
