from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class FeasibilityVerdict(str, Enum):
    advance = "advance"
    revise = "revise"
    reject = "reject"


class FeasibilityMemo(BaseModel):
    memo_id: str = Field(description="Unique memo identifier")
    report_id: str = Field(description="Associated ReviewReport ID")
    verdict: FeasibilityVerdict = Field(description="Feasibility verdict")
    gap_validity: str = Field(description="Whether the gap is genuinely valid")
    existing_progress: str = Field(description="Whether existing work is close to solving it")
    resource_assessment: str = Field(description="Whether resource requirements are reasonable")
    reasoning: str = Field(description="Overall reasoning")
    confidence: float = Field(ge=0, le=1, description="Confidence score")
    created_at: datetime = Field(description="Creation timestamp")
