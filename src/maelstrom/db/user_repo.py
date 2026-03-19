"""User repository — CRUD for users table."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite


async def create_user(
    db: aiosqlite.Connection, username: str, email: str, password_hash: str,
) -> dict:
    uid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO users (id, username, email, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
        (uid, username, email, password_hash, now),
    )
    await db.commit()
    return {"id": uid, "username": username, "email": email, "password_hash": password_hash, "created_at": now}


async def get_by_username(db: aiosqlite.Connection, username: str) -> dict | None:
    cur = await db.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def get_by_id(db: aiosqlite.Connection, user_id: str) -> dict | None:
    cur = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = await cur.fetchone()
    return dict(row) if row else None
