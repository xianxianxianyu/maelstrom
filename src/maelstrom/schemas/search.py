from __future__ import annotations

from pydantic import BaseModel, Field


class SourceStatus(BaseModel):
    source: str = Field(description="Source adapter name")
    status: str = Field(description="ok / timeout / error")
    count: int = Field(default=0, description="Number of results from this source")
    latency_ms: int = Field(default=0, description="Response latency in ms")
    error_msg: str | None = Field(default=None, description="Error message if failed")


class SearchResult(BaseModel):
    papers: list = Field(default_factory=list, description="List of PaperRecord")
    source_statuses: list[SourceStatus] = Field(
        default_factory=list, description="Per-source status"
    )
    is_degraded: bool = Field(default=False, description="True if some sources failed")
