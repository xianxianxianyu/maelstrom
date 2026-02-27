from __future__ import annotations

import uuid
from typing import Any

from .contracts_v1 import BudgetPolicy, PlanGraphV1, PlanNodeV1, PlanRequestV1, RetryPolicy, WorkerRole


class PlanAgentV1:
    def build_plan(self, request: PlanRequestV1) -> PlanGraphV1:
        stage2_sub_problems = list(request.stage2_result.get("sub_problems") or [])
        route_type = self._resolve_route_type(request.stage1_result, stage2_sub_problems)
        timeout_ms = int(request.options.get("timeout_ms") or 8000)
        per_node_timeout = max(800, min(5000, timeout_ms // 2))
        budget = BudgetPolicy(
            timeout_ms=per_node_timeout,
            max_context_chars=int(request.options.get("max_context_chars") or 4000),
        )

        nodes: list[PlanNodeV1] = []
        terminal_nodes: list[str] = []

        if stage2_sub_problems:
            for item in stage2_sub_problems:
                node_id = str(item.get("sub_problem_id") or f"node_{len(nodes) + 1}")
                capability = str(item.get("agent_capability") or "tool.mcp.execute")
                role = self._resolve_role(capability=capability, route_type=route_type)
                depends_on = [str(dep) for dep in item.get("depends_on", [])]
                node = PlanNodeV1(
                    node_id=node_id,
                    role=role,
                    capability=capability,
                    question=str(item.get("question") or request.query),
                    depends_on=depends_on,
                    tools=list(item.get("tools") or []),
                    parallel_group=item.get("parallel_group"),
                    budget=budget,
                    retry=RetryPolicy(max_attempts=2 if role in {WorkerRole.RESEARCHER, WorkerRole.MCP} else 1),
                    metadata={
                        "intent": item.get("intent"),
                        "route_type": item.get("route_type"),
                    },
                    identity_prompt=self._identity_prompt_for_role(role),
                )
                nodes.append(node)
                terminal_nodes.append(node_id)
        else:
            retrieve_id = "sp_research"
            response_id = "sp_response"
            nodes.extend(
                [
                    PlanNodeV1(
                        node_id=retrieve_id,
                        role=WorkerRole.RESEARCHER,
                        capability="context.retrieve",
                        question=request.query,
                        budget=budget,
                        identity_prompt=self._identity_prompt_for_role(WorkerRole.RESEARCHER),
                    ),
                    PlanNodeV1(
                        node_id=response_id,
                        role=WorkerRole.CODER,
                        capability="response.compose",
                        question=request.query,
                        depends_on=[retrieve_id],
                        budget=budget,
                        identity_prompt=self._identity_prompt_for_role(WorkerRole.CODER),
                    ),
                ]
            )
            terminal_nodes.append(response_id)

        if len(terminal_nodes) > 1:
            aggregate_id = "sp_aggregate"
            nodes.append(
                PlanNodeV1(
                    node_id=aggregate_id,
                    role=WorkerRole.AGGREGATOR,
                    capability="aggregate.merge",
                    question=request.query,
                    depends_on=terminal_nodes,
                    budget=budget,
                    identity_prompt=self._identity_prompt_for_role(WorkerRole.AGGREGATOR),
                )
            )
            verifier_depends = [aggregate_id]
        else:
            verifier_depends = terminal_nodes[-1:] if terminal_nodes else []

        nodes.append(
            PlanNodeV1(
                node_id="sp_verify",
                role=WorkerRole.VERIFIER,
                capability="grounding.verify",
                question=request.query,
                depends_on=verifier_depends,
                budget=BudgetPolicy(timeout_ms=min(2000, per_node_timeout), max_context_chars=budget.max_context_chars),
                identity_prompt=self._identity_prompt_for_role(WorkerRole.VERIFIER),
            )
        )

        return PlanGraphV1(
            plan_id=f"plan_{uuid.uuid4().hex[:12]}",
            nodes=nodes,
            metadata={
                "route_type": route_type,
                "query_len": len(request.query),
                "doc_scope": request.doc_scope,
            },
        )

    def _resolve_route_type(self, stage1_result: dict[str, Any], sub_problems: list[dict[str, Any]]) -> str:
        if sub_problems:
            route_types = {str(item.get("route_type") or "") for item in sub_problems}
            if "reasoning" in route_types:
                return "multi_hop"
            if "context_retrieval" in route_types:
                return "grounded"
        coarse_intent = str(stage1_result.get("coarse_intent") or "").upper()
        if coarse_intent == "CHAT":
            return "fast_path"
        if coarse_intent == "MULTI_PART":
            return "multi_hop"
        return "grounded"

    def _resolve_role(self, capability: str, route_type: str) -> WorkerRole:
        if capability.startswith("context.") or capability.startswith("research."):
            return WorkerRole.RESEARCHER
        if capability.startswith("reasoning.") or capability.startswith("response.") or capability.startswith("code."):
            return WorkerRole.CODER
        if capability.startswith("tool."):
            return WorkerRole.MCP
        if route_type == "fast_path":
            return WorkerRole.CODER
        return WorkerRole.MCP

    def _identity_prompt_for_role(self, role: WorkerRole) -> str:
        mapping = {
            WorkerRole.MCP: "你是 MCP Worker，负责工具调用与结构化返回，不给最终结论。",
            WorkerRole.RESEARCHER: "你是 Researcher Worker，负责检索、筛选和归纳证据。",
            WorkerRole.CODER: "你是 Coder Worker，负责推理整合与答案撰写。",
            WorkerRole.VERIFIER: "你是 Verifier Worker，负责证据一致性与正确性校验。",
            WorkerRole.AGGREGATOR: "你是 Aggregate Worker，负责聚合多路结果并保留引用。",
        }
        return mapping.get(role, "你是执行 Worker，按任务要求完成输出。")
