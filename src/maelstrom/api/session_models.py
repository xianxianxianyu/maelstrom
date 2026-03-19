from __future__ import annotations

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    title: str = Field(default="Untitled Session", description="Session title")


class SessionUpdateRequest(BaseModel):
    title: str | None = None


class SessionResponse(BaseModel):
    model_config = {"extra": "ignore"}

    id: str
    title: str
    status: str
    created_at: str
    updated_at: str
    run_count: int = 0
    latest_run_status: str | None = None
    latest_run_topic: str | None = None
    message_count: int = 0
    current_phase: str = "ideation"
