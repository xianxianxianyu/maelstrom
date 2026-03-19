from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ClaimType(str, Enum):
    method_effectiveness = "method_effectiveness"
    dataset_finding = "dataset_finding"
    metric_comparison = "metric_comparison"
    limitation = "limitation"
    assumption = "assumption"
    negative_result = "negative_result"


class Claim(BaseModel):
    claim_id: str = Field(description="Unique claim identifier")
    paper_id: str = Field(description="Source paper ID")
    claim_type: ClaimType = Field(description="Type of claim")
    text: str = Field(description="Claim text")
    evidence_refs: list[str] = Field(default_factory=list, description="Related evidence IDs")
    confidence: float = Field(ge=0, le=1, description="Confidence score")
    extracted_fields: dict = Field(default_factory=dict, description="Structured fields: problem/method/dataset/metric/result/limitation")
