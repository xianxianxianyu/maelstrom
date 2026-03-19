"""Intent classification schema — IntentType enum and ClassifiedIntent model."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    gap_discovery = "gap_discovery"
    qa_chat = "qa_chat"
    gap_followup = "gap_followup"
    share_to_qa = "share_to_qa"
    config = "config"
    synthesis = "synthesis"
    planning = "planning"
    experiment = "experiment"
    clarification_needed = "clarification_needed"


class SessionContext(BaseModel):
    """Lightweight session context for intent classification."""
    session_id: str
    has_gap_runs: bool = False
    has_indexed_docs: bool = False
    has_synthesis_runs: bool = False
    has_planning_runs: bool = False
    has_experiment_runs: bool = False
    recent_intent: IntentType | None = None


class ClassifiedIntent(BaseModel):
    intent: IntentType
    confidence: float = Field(ge=0, le=1)
    extracted_topic: str | None = None
    extracted_gap_ref: str | None = None
    reasoning: str = ""
    classifier_source: Literal["keyword", "llm"] = "keyword"
