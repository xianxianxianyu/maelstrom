"""Policies API — get/update governance policies per session."""
from __future__ import annotations

from fastapi import APIRouter

from maelstrom.db.database import get_db
from maelstrom.schemas.policy import PolicyConfig
from maelstrom.services import policy_service

router = APIRouter(prefix="/api/policies", tags=["policies"])


@router.get("/{session_id}")
async def get_policy(session_id: str):
    db = await get_db()
    config = await policy_service.get_policy_config(db, session_id)
    return config.model_dump()


@router.put("/{session_id}")
async def update_policy(session_id: str, body: PolicyConfig):
    db = await get_db()
    config = await policy_service.update_policy_config(db, session_id, body)
    return config.model_dump()
