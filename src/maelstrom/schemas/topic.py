from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TopicCandidate(BaseModel):
    candidate_id: str = Field(description="Unique candidate identifier")
    title: str = Field(description="Research topic title")
    related_gap_ids: list[str] = Field(description="Related gap IDs")
    recommended_next_step: str = Field(description="Suggested next action")
    risk_summary: str = Field(description="Risk assessment")
    session_id: str = Field(description="Owning session ID")
    created_at: datetime = Field(description="Creation timestamp")
