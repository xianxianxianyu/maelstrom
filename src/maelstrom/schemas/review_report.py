from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .claim import Claim
from .evidence import Evidence


class ConsensusPoint(BaseModel):
    statement: str = Field(description="Consensus statement")
    supporting_claim_ids: list[str] = Field(default_factory=list, description="Supporting claim IDs")
    strength: Literal["strong", "moderate", "weak"] = Field(default="moderate", description="Consensus strength")


class ConflictPoint(BaseModel):
    statement: str = Field(description="Conflict statement")
    claim_ids: list[str] = Field(default_factory=list, description="Conflicting claim IDs")
    conflict_source: str = Field(default="", description="Source of conflict, e.g. dataset_difference")
    requires_followup: bool = Field(default=False, description="Whether follow-up is needed")


class ReviewReport(BaseModel):
    report_id: str = Field(description="Unique report identifier")
    session_id: str = Field(description="Owning session ID")
    source_gap_id: str | None = Field(default=None, description="Source GapItem ID if from gap")
    topic: str = Field(description="Research topic")
    claims: list[Claim] = Field(default_factory=list, description="Extracted claims")
    evidences: list[Evidence] = Field(default_factory=list, description="Supporting evidences")
    consensus_points: list[ConsensusPoint] = Field(default_factory=list, description="Consensus points")
    conflict_points: list[ConflictPoint] = Field(default_factory=list, description="Conflict points")
    open_questions: list[str] = Field(default_factory=list, description="Open research questions")
    paper_count: int = Field(default=0, description="Number of papers analyzed")
    executive_summary: str | None = Field(default=None, description="Executive summary text")
    created_at: datetime = Field(description="Creation timestamp")
