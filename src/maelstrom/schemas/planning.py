"""Planning Engine schemas — ExperimentPlan, BaselineMatrix, AblationPlan, etc."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .common import RunStatus


class BaselineEntry(BaseModel):
    name: str = Field(description="Baseline method name")
    paper_id: str | None = Field(default=None, description="Source paper ID")
    description: str = Field(default="", description="Brief description")
    expected_performance: str = Field(default="", description="Expected performance range")


class BaselineMatrix(BaseModel):
    entries: list[BaselineEntry] = Field(default_factory=list)
    comparison_metrics: list[str] = Field(default_factory=list)


class AblationComponent(BaseModel):
    component: str = Field(description="Component to ablate")
    rationale: str = Field(default="", description="Why this ablation matters")
    expected_impact: str = Field(default="", description="Expected impact on results")


class AblationPlan(BaseModel):
    components: list[AblationComponent] = Field(default_factory=list)
    control_description: str = Field(default="", description="Full-model control description")


class DatasetProtocol(BaseModel):
    datasets: list[str] = Field(default_factory=list)
    preprocessing_steps: list[str] = Field(default_factory=list)
    split_strategy: str = Field(default="", description="Train/val/test split strategy")
    size_estimates: str = Field(default="", description="Estimated dataset sizes")


class MetricDefinition(BaseModel):
    name: str = Field(description="Metric name")
    formula: str = Field(default="", description="Metric formula or definition")
    higher_is_better: bool = Field(default=True)


class RiskItem(BaseModel):
    category: Literal["data", "compute", "methodology", "timeline", "other"] = "other"
    description: str = Field(description="Risk description")
    severity: Literal["low", "medium", "high"] = "medium"
    mitigation: str = Field(default="", description="Mitigation strategy")


class RiskMemo(BaseModel):
    memo_id: str = Field(description="Unique memo identifier")
    risks: list[RiskItem] = Field(default_factory=list)
    overall_risk_level: Literal["low", "medium", "high"] = "medium"
    recommendation: str = Field(default="")


class ChecklistItem(BaseModel):
    step: str = Field(description="Execution step description")
    category: str = Field(default="general")
    done: bool = Field(default=False)


class ExecutionChecklist(BaseModel):
    items: list[ChecklistItem] = Field(default_factory=list)


class ExperimentPlan(BaseModel):
    plan_id: str = Field(description="Unique plan identifier")
    session_id: str = Field(description="Owning session ID")
    source_synthesis_id: str | None = Field(default=None)
    topic: str = Field(description="Research topic")
    hypothesis: str = Field(default="", description="Primary hypothesis")
    variables: list[str] = Field(default_factory=list, description="Key variables")
    baselines: BaselineMatrix = Field(default_factory=BaselineMatrix)
    ablation: AblationPlan = Field(default_factory=AblationPlan)
    dataset_protocol: DatasetProtocol = Field(default_factory=DatasetProtocol)
    metrics: list[MetricDefinition] = Field(default_factory=list)
    checklist: ExecutionChecklist = Field(default_factory=ExecutionChecklist)
    risk_memo: RiskMemo | None = Field(default=None)
    created_at: datetime = Field(description="Creation timestamp")


class PlanningRunState(BaseModel):
    run_id: str = Field(description="Unique run identifier")
    session_id: str = Field(description="Owning session ID")
    source_synthesis_id: str | None = Field(default=None)
    topic: str = Field(description="Research topic")
    status: RunStatus = Field(default=RunStatus.pending)
    hypothesis: str = Field(default="")
    variables: list[str] = Field(default_factory=list)
    baselines: BaselineMatrix | None = Field(default=None)
    ablation: AblationPlan | None = Field(default=None)
    dataset_protocol: DatasetProtocol | None = Field(default=None)
    metrics: list[MetricDefinition] = Field(default_factory=list)
    checklist: ExecutionChecklist | None = Field(default=None)
    risk_memo: RiskMemo | None = Field(default=None)
    plan: ExperimentPlan | None = Field(default=None)
    current_step: str = Field(default="pending")
    error: str | None = Field(default=None)
    created_at: datetime = Field(description="Creation timestamp")
    completed_at: datetime | None = Field(default=None)
