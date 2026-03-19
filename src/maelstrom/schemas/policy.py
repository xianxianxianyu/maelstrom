"""Policy schemas for governance configuration."""
from __future__ import annotations

from pydantic import BaseModel


class PolicyConfig(BaseModel):
    # HITL approval gates
    feasibility_approval: bool = False
    plan_approval: bool = True
    conclusion_review: bool = True
    # Automation controls
    auto_advance_phase: bool = True
    allow_external_retrieval: bool = True
    auto_evidence_writeback: bool = True
