from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from .contracts_v1 import (
    NodeStatus,
    PlanExecutionResultV1,
    PlanGraphV1,
    PlanRequestV1,
    WorkerResultV1,
    WorkerRunContextV1,
    WorkerTaskV1,
)
from .worker_router_v1 import WorkerRouterV1

logger = logging.getLogger(__name__)


class DAGRunnerV1:
    def __init__(self, router: WorkerRouterV1) -> None:
        self.router = router

    async def run_plan(
        self,
        request: PlanRequestV1,
        plan: PlanGraphV1,
        selected_context: list[dict[str, Any]],
        event_callback: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> PlanExecutionResultV1:
        logger.info(
            "qa_dag_run_start",
            extra={
                "trace_id": request.trace_id,
                "session_id": request.session_id,
                "turn_id": request.turn_id,
                "plan_id": plan.plan_id,
                "node_count": len(plan.nodes),
            },
        )
        node_map = {node.node_id: node for node in plan.nodes}
        status_map = {node.node_id: NodeStatus.PENDING for node in plan.nodes}
        output_map: dict[str, dict[str, Any]] = {}
        citations: list[dict[str, Any]] = []
        run_records: list[dict[str, Any]] = []
        context = WorkerRunContextV1(
            session_id=request.session_id,
            turn_id=request.turn_id,
            trace_id=request.trace_id,
            selected_context=selected_context,
        )

        total_nodes = max(1, len(plan.nodes))
        completed_nodes = 0

        for batch in self._topological_batches(plan):
            batch_tasks = [
                self._run_node(
                    request=request,
                    node=node_map[node_id],
                    status_map=status_map,
                    output_map=output_map,
                    run_records=run_records,
                    context=context,
                    event_callback=event_callback,
                    total_nodes=total_nodes,
                )
                for node_id in batch
            ]
            batch_results = await asyncio.gather(*batch_tasks)
            for result in batch_results:
                if result is None:
                    continue
                citations.extend(result.citations)
            completed_nodes = sum(
                1
                for status in status_map.values()
                if status in {NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.SKIPPED}
            )
            if event_callback:
                progress = int((completed_nodes / total_nodes) * 100)
                await maybe_await(
                    event_callback(
                        {
                            "type": "dag.progress",
                            "trace_id": request.trace_id,
                            "progress": progress,
                            "completed": completed_nodes,
                            "total": total_nodes,
                        }
                    )
                )

            if any(status_map[node_id] == NodeStatus.FAILED for node_id in batch):
                logger.warning(
                    "qa_dag_stop_on_failed_batch",
                    extra={
                        "trace_id": request.trace_id,
                        "plan_id": plan.plan_id,
                        "failed_batch": batch,
                    },
                )
                break

        answer = self._build_answer(output_map, run_records)
        if run_records:
            success_count = sum(1 for run in run_records if run.get("success"))
            confidence = round(success_count / len(run_records), 4)
        else:
            confidence = 0.0

        result = PlanExecutionResultV1(
            answer=answer,
            citations=citations,
            confidence=confidence,
            node_runs=run_records,
            fallback_used=False,
        )
        logger.info(
            "qa_dag_run_done",
            extra={
                "trace_id": request.trace_id,
                "plan_id": plan.plan_id,
                "run_count": len(run_records),
                "citation_count": len(citations),
                "confidence": confidence,
            },
        )
        return result

    async def _run_node(
        self,
        request: PlanRequestV1,
        node,
        status_map: dict[str, NodeStatus],
        output_map: dict[str, dict[str, Any]],
        run_records: list[dict[str, Any]],
        context: WorkerRunContextV1,
        event_callback: Callable[[dict[str, Any]], Awaitable[None] | None] | None,
        total_nodes: int,
    ) -> WorkerResultV1 | None:
        dep_results = {dep: output_map.get(dep) for dep in node.depends_on}
        if any(dep_results.get(dep) is None for dep in node.depends_on):
            status_map[node.node_id] = NodeStatus.SKIPPED
            run_records.append(
                {
                    "sub_problem_id": node.node_id,
                    "capability": node.capability,
                    "agent": "worker-router-v1",
                    "success": False,
                    "error": "dependency missing",
                    "output": {},
                    "role": node.role.value,
                    "status": NodeStatus.SKIPPED.value,
                }
            )
            return None

        worker = self.router.resolve(role=node.role, capability=node.capability)
        logger.info(
            "qa_dag_node_start",
            extra={
                "trace_id": request.trace_id,
                "node_id": node.node_id,
                "role": node.role.value,
                "capability": node.capability,
                "depends_on": list(node.depends_on),
            },
        )
        task_prompt = build_task_prompt(node.question, node.capability, node.tools)
        task = WorkerTaskV1(
            task_id=f"task_{uuid.uuid4().hex[:10]}",
            node_id=node.node_id,
            role=node.role,
            capability=node.capability,
            query=node.question,
            payload={
                "query": request.query,
                "question": node.question,
                "route_type": str(plan_route_type(request=request)),
                "stage1_result": request.stage1_result,
                "stage2_result": request.stage2_result,
                "tools": node.tools,
            },
            dependencies=dep_results,
            budget=node.budget,
            metadata=node.metadata,
            task_prompt=task_prompt,
        )

        if node.capability == "grounding.verify":
            upstream = [value for value in dep_results.values() if isinstance(value, dict)]
            candidate = upstream[-1] if upstream else {}
            task.payload["answer"] = str(candidate.get("answer") or candidate.get("summary") or "")
            task.payload["citations"] = list(candidate.get("citations") or [])
            task.payload["evidence_items"] = selected_context_to_evidence(context.selected_context)

        max_attempts = max(1, node.retry.max_attempts)
        last_error = ""
        start = time.perf_counter()
        status_map[node.node_id] = NodeStatus.RUNNING
        if event_callback:
            await maybe_await(
                event_callback(
                    {
                        "type": "worker.started",
                        "trace_id": request.trace_id,
                        "node_id": node.node_id,
                        "worker": worker.name,
                        "role": node.role.value,
                        "capability": node.capability,
                        "identity_prompt": str(getattr(worker, "identity_prompt", "")),
                        "task_prompt": task_prompt,
                        "progress": 5,
                    }
                )
            )

        for attempt in range(1, max_attempts + 1):
            try:
                timeout_sec = max(0.1, node.budget.timeout_ms / 1000.0)
                result = await asyncio.wait_for(worker.run(task, context), timeout=timeout_sec)

                if node.capability == "grounding.verify":
                    result = self._enrich_verify_payload(result=result, dep_results=dep_results)

                output_map[node.node_id] = dict(result.output)
                if result.citations and "citations" not in output_map[node.node_id]:
                    output_map[node.node_id]["citations"] = result.citations
                status_map[node.node_id] = NodeStatus.COMPLETED if result.success else NodeStatus.FAILED
                run_records.append(
                    {
                        "sub_problem_id": node.node_id,
                        "capability": node.capability,
                        "agent": worker.name,
                        "success": result.success,
                        "error": result.error,
                        "output": result.output,
                        "role": node.role.value,
                        "status": status_map[node.node_id].value,
                        "attempt": attempt,
                        "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                        "identity_prompt": str(getattr(worker, "identity_prompt", "")),
                        "task_prompt": task_prompt,
                        "progress": 100 if result.success else 0,
                        "artifact_preview": build_artifact_preview(result.output),
                    }
                )
                logger.info(
                    "qa_dag_node_done",
                    extra={
                        "trace_id": request.trace_id,
                        "node_id": node.node_id,
                        "role": node.role.value,
                        "capability": node.capability,
                        "success": result.success,
                        "attempt": attempt,
                        "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                    },
                )
                if event_callback:
                    completed_count = sum(
                        1
                        for status in status_map.values()
                        if status in {NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.SKIPPED}
                    )
                    await maybe_await(
                        event_callback(
                            {
                                "type": "worker.completed" if result.success else "worker.failed",
                                "trace_id": request.trace_id,
                                "node_id": node.node_id,
                                "worker": worker.name,
                                "role": node.role.value,
                                "capability": node.capability,
                                "success": result.success,
                                "error": result.error,
                                "artifact_preview": build_artifact_preview(result.output),
                                "progress": int((completed_count / max(1, total_nodes)) * 100),
                            }
                        )
                    )
                return result
            except Exception as exc:
                last_error = str(exc)
                if attempt < max_attempts and node.retry.backoff_ms > 0:
                    await asyncio.sleep(node.retry.backoff_ms / 1000.0)

        status_map[node.node_id] = NodeStatus.FAILED
        run_records.append(
            {
                "sub_problem_id": node.node_id,
                "capability": node.capability,
                "agent": worker.name,
                "success": False,
                "error": last_error or "unknown error",
                "output": {},
                "role": node.role.value,
                "status": NodeStatus.FAILED.value,
                "attempt": max_attempts,
                "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                "identity_prompt": str(getattr(worker, "identity_prompt", "")),
                "task_prompt": task_prompt,
                "progress": 0,
                "artifact_preview": "",
            }
        )
        logger.warning(
            "qa_dag_node_failed",
            extra={
                "trace_id": request.trace_id,
                "node_id": node.node_id,
                "role": node.role.value,
                "capability": node.capability,
                "attempt": max_attempts,
                "error": last_error or "unknown error",
            },
        )
        if event_callback:
            await maybe_await(
                event_callback(
                    {
                        "type": "worker.failed",
                        "trace_id": request.trace_id,
                        "node_id": node.node_id,
                        "worker": worker.name,
                        "role": node.role.value,
                        "capability": node.capability,
                        "success": False,
                        "error": last_error or "unknown error",
                        "progress": 0,
                    }
                )
            )
        return WorkerResultV1(success=False, output={}, error=last_error or "unknown error", recoverable=True)

    def _enrich_verify_payload(
        self,
        result: WorkerResultV1,
        dep_results: dict[str, dict[str, Any] | None],
    ) -> WorkerResultV1:
        if result.output.get("passed") is None:
            upstream = [value for value in dep_results.values() if isinstance(value, dict)]
            if not upstream:
                result.success = False
                result.error = result.error or "verify dependency missing"
                return result
            candidate = upstream[-1]
            answer = str(candidate.get("answer") or candidate.get("summary") or "")
            citations = list(candidate.get("citations") or result.citations)
            passed = bool(answer.strip()) and bool(citations)
            result.output = {
                "passed": passed,
                "answer": answer if passed else "",
                "citations": citations if passed else [],
                "reasons": [] if passed else ["missing answer or citations"],
            }
            result.success = passed
            result.error = None if passed else "verify failed"
            result.citations = citations if passed else []
        return result

    def _build_answer(self, output_map: dict[str, dict[str, Any]], run_records: list[dict[str, Any]]) -> str:
        verify_outputs = [
            run.get("output")
            for run in run_records
            if run.get("capability") == "grounding.verify" and run.get("success")
        ]
        if verify_outputs:
            output = verify_outputs[-1] or {}
            answer = output.get("answer")
            if answer:
                return str(answer)

        if run_records:
            output = run_records[-1].get("output")
            if isinstance(output, dict):
                answer = output.get("answer") or output.get("summary") or output.get("text")
                if answer:
                    return str(answer)

        for value in output_map.values():
            if isinstance(value, dict):
                answer = value.get("answer") or value.get("summary") or value.get("text")
                if answer:
                    return str(answer)
        return "未生成有效结果"

    def _topological_batches(self, plan: PlanGraphV1) -> list[list[str]]:
        node_map = {node.node_id: node for node in plan.nodes}
        in_degree = {node.node_id: len(node.depends_on) for node in plan.nodes}
        remaining = set(node_map.keys())
        batches: list[list[str]] = []

        while remaining:
            ready = [node_id for node_id in remaining if in_degree[node_id] == 0]
            if not ready:
                raise ValueError("circular dependency in plan graph")
            batches.append(sorted(ready))
            for node_id in ready:
                remaining.remove(node_id)
                for other in remaining:
                    if node_id in node_map[other].depends_on:
                        in_degree[other] -= 1
        return batches


def plan_route_type(request: PlanRequestV1) -> str:
    stage2 = request.stage2_result
    if stage2:
        route_plan = stage2.get("routing_plan") or []
        capabilities = {str(item.get("capability") or "") for item in route_plan if isinstance(item, dict)}
        if "reasoning.synthesize" in capabilities:
            return "multi_hop"
        if "context.retrieve" in capabilities:
            return "grounded"
    intent = str(request.stage1_result.get("coarse_intent") or "").upper()
    if intent == "CHAT":
        return "chat"
    return "grounded"


def selected_context_to_evidence(selected_context: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "text": str(item.get("summary") or ""),
            "source": str(item.get("turn_id") or "unknown"),
            "score": float(item.get("score") or 0.0),
            "summary": str(item.get("summary") or ""),
        }
        for item in selected_context
    ]


def build_task_prompt(question: str, capability: str, tools: list[str]) -> str:
    tools_text = ", ".join(tools) if tools else "none"
    return (
        f"Capability: {capability}\n"
        f"Question: {question}\n"
        f"Tools: {tools_text}\n"
        "Please complete the task with concise and structured output."
    )


def build_artifact_preview(output: dict[str, Any]) -> str:
    if not isinstance(output, dict):
        return ""
    for key in ("answer", "summary", "text"):
        value = output.get(key)
        if isinstance(value, str) and value.strip():
            return value[:220]
    return ""


async def maybe_await(value: Awaitable[None] | None) -> None:
    if value is None:
        return
    await value
