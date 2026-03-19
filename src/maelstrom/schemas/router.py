"""Router schema — route decisions and responses."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .clarification import ClarificationRequest
from .intent import ClassifiedIntent


class RouterInput(BaseModel):
    session_id: str
    user_input: str = ""
    clarification_reply: dict | None = None


class RouterResponse(BaseModel):
    """Unified routing response — frontend decides rendering based on response_type."""
    response_type: Literal["stream", "clarification", "redirect", "error"]
    stream_url: str | None = None
    clarification: ClarificationRequest | None = None
    redirect_path: str | None = None
    error_message: str | None = None
    intent: ClassifiedIntent | None = None
