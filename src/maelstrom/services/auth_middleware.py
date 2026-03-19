"""Auth middleware — FastAPI dependencies for user extraction."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from maelstrom.db import user_repo
from maelstrom.db.database import get_db
from maelstrom.services.auth_service import decode_token


async def get_current_user(request: Request) -> dict:
    """Strict: requires valid token, raises 401 otherwise."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth[7:]
    data = decode_token(token)
    if not data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    db = await get_db()
    user = await user_repo.get_by_id(db, data["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_optional_user(request: Request) -> dict | None:
    """Lenient: returns user if token present, None otherwise. Backward compatible."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    data = decode_token(token)
    if not data:
        return None
    db = await get_db()
    return await user_repo.get_by_id(db, data["sub"])
