from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GapScores(BaseModel):
    novelty: float = Field(ge=0, le=1, description="Novelty score")
    feasibility: float = Field(ge=0, le=1, description="Feasibility score")
    impact: float = Field(ge=0, le=1, description="Impact score")


class GapItem(BaseModel):
    gap_id: str = Field(description="Unique gap identifier")
    title: str = Field(description="Gap title")
    summary: str = Field(description="Gap description")
    gap_type: list[str] = Field(description="Gap categories (dataset/evaluation/method/...)")
    evidence_refs: list[str] = Field(default_factory=list, description="Supporting paper IDs")
    confidence: float = Field(ge=0, le=1, description="Confidence score")
    scores: GapScores = Field(description="Detailed scores")
    session_id: str = Field(description="Owning session ID")
    created_at: datetime = Field(description="Creation timestamp")
