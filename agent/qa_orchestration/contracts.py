from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class SubagentTask:
    task_id: str
    turn_id: str
    query: str
    capability: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class SubagentRunContext:
    session_id: str
    trace_id: str
    selected_context: list[dict[str, Any]] = field(default_factory=list)
    dependency_results: dict[str, Any] = field(default_factory=dict)


@dataclass
class SubagentResult:
    success: bool
    output: dict[str, Any]
    citations: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class Subagent(Protocol):
    name: str
    capabilities: set[str]

    async def run(self, task: SubagentTask, context: SubagentRunContext) -> SubagentResult:
        ...
