from __future__ import annotations

import uuid
from typing import Optional

from agent.core.types import NodeType, QAPlan, QAPlanNode, RouteType


class PlanAgentV2:
    async def build_plan(self, query: str, route: RouteType, doc_id: Optional[str]) -> QAPlan:
        plan_id = f"plan_{uuid.uuid4().hex[:12]}"

        if route == RouteType.FAST_PATH:
            nodes = [
                QAPlanNode(node_id="write", node_type=NodeType.WRITE),
                QAPlanNode(node_id="verify", node_type=NodeType.VERIFY, dependencies=["write"]),
            ]
        elif route == RouteType.MULTI_HOP:
            nodes = [
                QAPlanNode(node_id="retrieve_primary", node_type=NodeType.RETRIEVE),
                QAPlanNode(node_id="retrieve_secondary", node_type=NodeType.RETRIEVE),
                QAPlanNode(
                    node_id="reason",
                    node_type=NodeType.REASON,
                    dependencies=["retrieve_primary", "retrieve_secondary"],
                ),
                QAPlanNode(node_id="write", node_type=NodeType.WRITE, dependencies=["reason"]),
                QAPlanNode(node_id="verify", node_type=NodeType.VERIFY, dependencies=["write"]),
            ]
        else:
            nodes = [
                QAPlanNode(node_id="retrieve", node_type=NodeType.RETRIEVE),
                QAPlanNode(node_id="write", node_type=NodeType.WRITE, dependencies=["retrieve"]),
                QAPlanNode(node_id="verify", node_type=NodeType.VERIFY, dependencies=["write"]),
            ]

        return QAPlan(
            plan_id=plan_id,
            nodes=nodes,
            metadata={
                "route": route.value,
                "query_len": len(query),
                "doc_id": doc_id,
            },
        )
