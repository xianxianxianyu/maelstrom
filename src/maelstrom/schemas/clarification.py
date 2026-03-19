"""Clarification protocol — schema for structured follow-up questions."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .intent import IntentType


class ClarificationOption(BaseModel):
    label: str = Field(description="Display text for the option")
    intent: IntentType = Field(description="Mapped intent type")
    description: str = Field(default="", description="Additional explanation")


class ClarificationRequest(BaseModel):
    request_id: str = Field(description="Unique clarification request ID")
    question: str = Field(description="The clarification question text")
    options: list[ClarificationOption] = Field(description="2-4 selectable options")
    allow_freetext: bool = Field(default=True, description="Allow free-text input")
    original_input: str = Field(description="User's original input")
    session_id: str = Field(description="Owning session ID")
