"""Eval schemas — request/response models for eval API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class EvalRunRequest(BaseModel):
    mode: Literal["regression", "replay", "runtime_metrics"]
    engine_filter: str | None = None
    target_run_id: str | None = None
    target_session_id: str | None = None


class EvalCaseResultOut(BaseModel):
    id: str
    case_id: str
    engine: str
    passed: bool
    schema_valid: bool
    quality_checks: dict
    error: str | None
    created_at: str


class EvalRunOut(BaseModel):
    id: str
    mode: str
    status: str
    engine_filter: str | None
    target_run_id: str | None
    target_session_id: str | None
    summary: dict
    created_at: str
    completed_at: str | None


class RuntimeMetricsOut(BaseModel):
    run_id: str | None
    session_id: str | None
    engine: str
    total_duration_ms: float | None
    step_durations: dict[str, float]
    step_count: int
    error_count: int
    tool_call_count: int
