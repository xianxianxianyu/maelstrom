"""Approvals API — list, get, resolve approvals."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from maelstrom.db import approval_repo
from maelstrom.db.database import get_db
from maelstrom.schemas.approval import ApprovalResolution
from maelstrom.services.auth_middleware import get_optional_user
from maelstrom.services.hitl_manager import get_hitl_manager

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("")
async def list_approvals(session_id: str | None = None, status: str = "pending"):
    db = await get_db()
    if status == "all":
        return await approval_repo.list_all(db, session_id)
    return await approval_repo.list_pending(db, session_id)


@router.get("/{approval_id}")
async def get_approval(approval_id: str):
    db = await get_db()
    record = await approval_repo.get_approval(db, approval_id)
    if not record:
        raise HTTPException(status_code=404, detail="Approval not found")
    return record


@router.post("/{approval_id}/resolve")
async def resolve_approval(
    approval_id: str,
    body: ApprovalResolution,
    user: dict | None = Depends(get_optional_user),
):
    db = await get_db()
    resolved_by = body.resolved_by or (user["username"] if user else "anonymous")
    manager = get_hitl_manager()
    record = await manager.resolve_approval(db, approval_id, body.decision, resolved_by)
    if not record:
        raise HTTPException(status_code=404, detail="Approval not found")
    return record
