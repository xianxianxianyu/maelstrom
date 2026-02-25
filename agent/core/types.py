from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class RouteType(str, Enum):
    FAST_PATH = "FAST_PATH"
    DOC_GROUNDED = "DOC_GROUNDED"
    MULTI_HOP = "MULTI_HOP"


class NodeType(str, Enum):
    RETRIEVE = "RETRIEVE"
    REASON = "REASON"
    WRITE = "WRITE"
    VERIFY = "VERIFY"


class NodeStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class ContextBlock:
    type: str
    data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidencePack:
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Citation:
    chunk_id: str
    text: str
    score: float


@dataclass
class TraceEvent:
    timestamp: str
    event_type: str
    data: Dict[str, Any]


@dataclass
class TraceContext:
    trace_id: str = field(default_factory=lambda: f"trace_{uuid.uuid4().hex[:20]}")
    start_time: datetime = field(default_factory=datetime.utcnow)
    events: List[TraceEvent] = field(default_factory=list)

    def log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        self.events.append(
            TraceEvent(
                timestamp=datetime.utcnow().isoformat(),
                event_type=event_type,
                data=data,
            )
        )

    @property
    def duration_ms(self) -> float:
        return (datetime.utcnow() - self.start_time).total_seconds() * 1000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "start_time": self.start_time.isoformat(),
            "duration_ms": self.duration_ms,
            "event_count": len(self.events),
            "events": [
                {
                    "timestamp": event.timestamp,
                    "type": event.event_type,
                    "data": event.data,
                }
                for event in self.events
            ],
        }


@dataclass
class QAPlanNode:
    node_id: str
    node_type: NodeType
    dependencies: List[str] = field(default_factory=list)
    budget_hints: Dict[str, Any] = field(default_factory=dict)
    status: NodeStatus = NodeStatus.PENDING
    result: Any = None
    error: Optional[str] = None


@dataclass
class QAPlan:
    plan_id: str
    nodes: List[QAPlanNode] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DAGNode:
    node_id: str
    func: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    result: Any = None
    error: Optional[str] = None


class DAGExecutor:
    def __init__(self) -> None:
        self.nodes: Dict[str, DAGNode] = {}

    def add_node(
        self,
        node_id: str,
        func: Callable,
        args: tuple = (),
        kwargs: Optional[Dict[str, Any]] = None,
        dependencies: Optional[List[str]] = None,
    ) -> DAGNode:
        node = DAGNode(
            node_id=node_id,
            func=func,
            args=args,
            kwargs=kwargs or {},
            dependencies=dependencies or [],
        )
        self.nodes[node_id] = node
        return node

    async def execute(self) -> Dict[str, Any]:
        execution_order = self._topological_sort()
        results: Dict[str, Any] = {}

        for node_id in execution_order:
            node = self.nodes[node_id]
            deps_satisfied = all(
                self.nodes[dep].status == NodeStatus.COMPLETED for dep in node.dependencies
            )
            if not deps_satisfied:
                node.status = NodeStatus.FAILED
                node.error = "Dependencies not satisfied"
                continue

            try:
                node.status = NodeStatus.RUNNING
                node_kwargs = node.kwargs.copy()
                for dep in node.dependencies:
                    node_kwargs[f"{dep}_result"] = self.nodes[dep].result

                if asyncio.iscoroutinefunction(node.func):
                    result = await node.func(*node.args, **node_kwargs)
                else:
                    result = node.func(*node.args, **node_kwargs)

                node.result = result
                node.status = NodeStatus.COMPLETED
                results[node_id] = result
            except Exception as exc:
                node.status = NodeStatus.FAILED
                node.error = str(exc)
                logger.error("DAG node %s failed: %s", node_id, exc)

        return results

    def _topological_sort(self) -> List[str]:
        in_degree = {node_id: 0 for node_id in self.nodes}
        for node in self.nodes.values():
            for dep in node.dependencies:
                if dep in self.nodes:
                    in_degree[node.node_id] += 1

        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        sorted_nodes: List[str] = []

        while queue:
            node_id = queue.pop(0)
            sorted_nodes.append(node_id)
            for node in self.nodes.values():
                if node_id in node.dependencies:
                    in_degree[node.node_id] -= 1
                    if in_degree[node.node_id] == 0:
                        queue.append(node.node_id)

        if len(sorted_nodes) != len(self.nodes):
            raise ValueError("Circular dependency detected in DAG")
        return sorted_nodes


__all__ = [
    "RouteType",
    "NodeType",
    "NodeStatus",
    "ContextBlock",
    "EvidencePack",
    "Citation",
    "TraceEvent",
    "TraceContext",
    "QAPlanNode",
    "QAPlan",
    "DAGNode",
    "DAGExecutor",
]
