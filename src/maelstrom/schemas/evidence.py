from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    evidence_id: str = Field(description="Unique evidence identifier")
    source_id: str = Field(description="Source paper ID")
    source_span: str = Field(default="", description="Location in source, e.g. 'page 4, paragraph 2'")
    snippet: str = Field(description="Original text snippet")
    modality: Literal["text", "table", "figure"] = Field(default="text", description="Content modality")
    retrieved_via: str = Field(default="", description="Retrieval source tag")
    created_at: datetime = Field(description="Creation timestamp")
