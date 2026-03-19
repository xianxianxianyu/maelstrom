from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .common import RunStatus
from .gap import GapItem
from .paper import PaperRecord
from .search import SearchResult
from .topic import TopicCandidate


class GapAnalysisResult(BaseModel):
    run_id: str = Field(description="Unique run identifier")
    session_id: str = Field(description="Owning session ID")
    topic: str = Field(description="Input topic")
    status: RunStatus = Field(description="Run status")
    papers: list[PaperRecord] = Field(
        default_factory=list,
        description="Full list of retrieved papers (not just IDs)",
    )
    search_result: SearchResult = Field(
        default_factory=SearchResult, description="Search metadata"
    )
    coverage_matrix: dict[str, Any] = Field(
        default_factory=dict,
        description="Full coverage matrix (not just summary)",
    )
    ranked_gaps: list[GapItem] = Field(
        default_factory=list,
        description="Full ranked GapItem objects (not just IDs)",
    )
    topic_candidates: list[TopicCandidate] = Field(
        default_factory=list,
        description="Full TopicCandidate objects (not just IDs)",
    )
    created_at: datetime = Field(description="Run start timestamp")
    completed_at: datetime | None = Field(default=None, description="Run completion timestamp")
