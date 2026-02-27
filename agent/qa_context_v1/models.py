from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


TurnStatus = Literal["pending", "clarification_pending", "completed", "failed"]
ClarificationStatus = Literal["pending", "resolved", "timeout"]


@dataclass
class Stage1Result:
    coarse_intent: str
    confidence: float
    relevant_context_ids: list[str] = field(default_factory=list)
    selection_reasoning: str = ""
    suggested_doc_scope: list[str] = field(default_factory=list)
    needs_refinement: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Stage2SubProblem:
    sub_problem_id: str
    question: str
    intent: str
    entities: list[str]
    route_type: str
    agent_capability: str
    tools: list[str] = field(default_factory=list)
    complexity: str = "simple"
    depends_on: list[str] = field(default_factory=list)
    parallel_group: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Stage2Result:
    sub_problems: list[Stage2SubProblem]
    routing_plan: list[dict[str, Any]]
    clarification_needed: bool = False
    clarification_question: str | None = None
    clarification_options: list[str] = field(default_factory=list)
    overall_confidence: float = 0.7

    def to_dict(self) -> dict[str, Any]:
        return {
            "sub_problems": [item.to_dict() for item in self.sub_problems],
            "routing_plan": self.routing_plan,
            "clarification_needed": self.clarification_needed,
            "clarification_question": self.clarification_question,
            "clarification_options": self.clarification_options,
            "overall_confidence": self.overall_confidence,
        }


@dataclass
class DialogueTurn:
    turn_id: str
    session_id: str
    created_at: str
    updated_at: str
    user_query: str
    assistant_answer: str | None = None
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    topic_tags: list[str] = field(default_factory=list)
    intent_tag: str = "UNKNOWN"
    entities: list[dict[str, Any]] = field(default_factory=list)
    referenced_docs: list[str] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    stage1_result: dict[str, Any] = field(default_factory=dict)
    stage2_result: dict[str, Any] = field(default_factory=dict)
    routing_plan: list[dict[str, Any]] = field(default_factory=list)
    agent_runs: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    trace_id: str = ""
    status: TurnStatus = "pending"
    clarification_thread_id: str | None = None
    error: str | None = None
    schema_version: str = "qa-turn-v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClarificationThread:
    thread_id: str
    session_id: str
    turn_id: str
    created_at: str
    updated_at: str
    original_query: str
    question: str
    options: list[str] = field(default_factory=list)
    ambiguity_points: list[str] = field(default_factory=list)
    status: ClarificationStatus = "pending"
    answer: str | None = None
    resolved_query: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class KernelResponse:
    status: str
    session_id: str
    turn_id: str
    trace_id: str
    answer: str | None = None
    summary: str | None = None
    tags: list[str] = field(default_factory=list)
    intent_tag: str = "UNKNOWN"
    confidence: float = 0.0
    stage1_result: dict[str, Any] = field(default_factory=dict)
    stage2_result: dict[str, Any] = field(default_factory=dict)
    clarification: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QueryRequest:
    query: str
    session_id: str | None = None
    doc_scope: list[str] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)
