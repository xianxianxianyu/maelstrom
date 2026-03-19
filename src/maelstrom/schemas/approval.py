"""Approval schemas for HITL governance."""
from __future__ import annotations

from pydantic import BaseModel


class ApprovalRequest(BaseModel):
    id: str = ""
    session_id: str
    run_id: str
    approval_type: str
    status: str = "pending"
    payload_json: str = "{}"
    requested_at: str = ""
    resolved_at: str | None = None
    resolved_by: str | None = None


class ApprovalResolution(BaseModel):
    decision: str  # "approved" | "rejected"
    comment: str = ""
    resolved_by: str = ""
