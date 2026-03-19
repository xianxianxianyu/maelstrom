from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .claim import Claim
from .common import RunStatus
from .evidence import Evidence
from .feasibility import FeasibilityMemo
from .paper import PaperRecord
from .review_report import ConflictPoint, ConsensusPoint, ReviewReport


class SynthesisRunState(BaseModel):
    run_id: str = Field(description="Unique run identifier")
    session_id: str = Field(description="Owning session ID")
    source_gap_id: str | None = Field(default=None, description="Source GapItem ID if from gap")
    topic: str = Field(description="Research topic")
    status: RunStatus = Field(default=RunStatus.pending, description="Run status")
    # Pipeline state
    targeted_papers: list[PaperRecord] = Field(default_factory=list, description="Papers from targeted retrieval")
    filtered_papers: list[PaperRecord] = Field(default_factory=list, description="Papers after relevance filtering")
    claims: list[Claim] = Field(default_factory=list, description="Extracted claims")
    evidences: list[Evidence] = Field(default_factory=list, description="Extracted evidences")
    consensus_points: list[ConsensusPoint] = Field(default_factory=list, description="Consensus points")
    conflict_points: list[ConflictPoint] = Field(default_factory=list, description="Conflict points")
    review_report: ReviewReport | None = Field(default=None, description="Final review report")
    feasibility_memo: FeasibilityMemo | None = Field(default=None, description="Feasibility memo")
    # Metadata
    current_step: str = Field(default="pending", description="Current pipeline step name")
    error: str | None = Field(default=None, description="Error message if failed")
    created_at: datetime = Field(description="Creation timestamp")
    completed_at: datetime | None = Field(default=None, description="Completion timestamp")
