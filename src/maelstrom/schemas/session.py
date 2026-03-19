from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .common import SessionStatus


class Session(BaseModel):
    session_id: str = Field(description="Unique session identifier")
    title: str = Field(default="Untitled Session", description="Session title")
    status: SessionStatus = Field(default=SessionStatus.active, description="Session status")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")
    artifact_refs: list[str] = Field(default_factory=list, description="Associated artifact IDs")
    gap_runs: list[str] = Field(default_factory=list, description="Associated gap run IDs")
    chat_message_count: int = Field(default=0, description="Number of chat messages")
    indexed_doc_count: int = Field(default=0, description="Number of indexed documents")
