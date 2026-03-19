"""Trace event schema for the unified Event Bus."""
from __future__ import annotations

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    id: str = ""
    run_id: str
    session_id: str = ""
    engine: str = ""
    event_type: str
    node_name: str | None = None
    timestamp: str = ""
    payload_json: str = "{}"
