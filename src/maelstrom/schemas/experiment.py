"""Experiment Engine schemas — RunRecord, Conclusion, ReflectionNote, etc."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .common import RunStatus


class MetricResult(BaseModel):
    name: str = Field(description="Metric name")
    value: float = Field(description="Metric value")
    baseline_value: float | None = Field(default=None)
    is_improvement: bool | None = Field(default=None)


class RunRecord(BaseModel):
    record_id: str = Field(description="Unique record identifier")
    plan_id: str = Field(description="Source ExperimentPlan ID")
    config_snapshot: dict = Field(default_factory=dict, description="Frozen config from plan")
    metrics: list[MetricResult] = Field(default_factory=list)
    notes: str = Field(default="")
    created_at: datetime = Field(description="Creation timestamp")


class ClaimVerdict(BaseModel):
    claim_id: str = Field(description="Original claim ID")
    claim_text: str = Field(default="")
    supported: bool | None = Field(default=None)
    reasoning: str = Field(default="")


class Conclusion(BaseModel):
    conclusion_id: str = Field(description="Unique conclusion identifier")
    session_id: str = Field(description="Owning session ID")
    summary: str = Field(default="", description="Conclusion summary")
    key_findings: list[str] = Field(default_factory=list)
    claim_verdicts: list[ClaimVerdict] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    created_at: datetime = Field(description="Creation timestamp")


class ReflectionNote(BaseModel):
    note_id: str = Field(description="Unique note identifier")
    session_id: str = Field(description="Owning session ID")
    insights: list[str] = Field(default_factory=list, description="Key insights")
    new_gaps: list[str] = Field(default_factory=list, description="Newly identified gaps")
    methodology_notes: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    created_at: datetime = Field(description="Creation timestamp")


class ExperimentRunState(BaseModel):
    run_id: str = Field(description="Unique run identifier")
    session_id: str = Field(description="Owning session ID")
    source_plan_id: str | None = Field(default=None)
    topic: str = Field(description="Research topic")
    status: RunStatus = Field(default=RunStatus.pending)
    config_snapshot: dict = Field(default_factory=dict)
    metrics: list[MetricResult] = Field(default_factory=list)
    normalized_metrics: list[dict] = Field(default_factory=list)
    conclusion: Conclusion | None = Field(default=None)
    claim_verdicts: list[ClaimVerdict] = Field(default_factory=list)
    reflection: ReflectionNote | None = Field(default=None)
    current_step: str = Field(default="pending")
    error: str | None = Field(default=None)
    created_at: datetime = Field(description="Creation timestamp")
    completed_at: datetime | None = Field(default=None)
