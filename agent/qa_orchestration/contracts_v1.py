from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Protocol


class WorkerRole(str, Enum):
    MCP = "MCP"
    RESEARCHER = "RESEARCHER"
    CODER = "CODER"
    VERIFIER = "VERIFIER"
    AGGREGATOR = "AGGREGATOR"


class NodeStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class RetryPolicy:
    max_attempts: int = 1
    backoff_ms: int = 0


@dataclass
class BudgetPolicy:
    timeout_ms: int = 4000
    max_context_chars: int = 4000


@dataclass
class PlanNodeV1:
    node_id: str
    role: WorkerRole
    capability: str
    question: str
    depends_on: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    parallel_group: str | None = None
    budget: BudgetPolicy = field(default_factory=BudgetPolicy)
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    metadata: dict[str, Any] = field(default_factory=dict)
    identity_prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["role"] = self.role.value
        return payload


@dataclass
class PlanGraphV1:
    plan_id: str
    nodes: list[PlanNodeV1]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "nodes": [node.to_dict() for node in self.nodes],
            "metadata": self.metadata,
        }


@dataclass
class PlanRequestV1:
    query: str
    session_id: str
    turn_id: str
    trace_id: str
    doc_scope: list[str] = field(default_factory=list)
    stage1_result: dict[str, Any] = field(default_factory=dict)
    stage2_result: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkerTaskV1:
    task_id: str
    node_id: str
    role: WorkerRole
    capability: str
    query: str
    payload: dict[str, Any] = field(default_factory=dict)
    dependencies: dict[str, Any] = field(default_factory=dict)
    budget: BudgetPolicy = field(default_factory=BudgetPolicy)
    metadata: dict[str, Any] = field(default_factory=dict)
    task_prompt: str = ""


@dataclass
class WorkerRunContextV1:
    session_id: str
    turn_id: str
    trace_id: str
    selected_context: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class WorkerResultV1:
    success: bool
    output: dict[str, Any] = field(default_factory=dict)
    citations: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    recoverable: bool = True
    metrics: dict[str, Any] = field(default_factory=dict)
    progress: int = 100


@dataclass
class PlanExecutionResultV1:
    answer: str
    citations: list[dict[str, Any]]
    confidence: float
    node_runs: list[dict[str, Any]]
    fallback_used: bool = False


class WorkerV1(Protocol):
    name: str
    role: WorkerRole
    capabilities: set[str]

    async def run(self, task: WorkerTaskV1, context: WorkerRunContextV1) -> WorkerResultV1:
        raise NotImplementedError
