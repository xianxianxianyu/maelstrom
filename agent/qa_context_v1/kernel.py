from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from typing import Any

from agent.event_bus import get_event_bus
from agent.qa_orchestration import DAGRunnerV1, PlanAgentV1, WorkerRegistryV1, WorkerRouterV1
from agent.qa_orchestration.contracts_v1 import PlanRequestV1
from agent.qa_orchestration.subagent_registry import SubagentRegistry
from agent.qa_orchestration.subagent_runner import (
    ReasoningSubagent,
    ResponseSubagent,
    RetrievalSubagent,
    SubagentRunner,
)
from agent.qa_orchestration.workers import (
    AggregateWorkerV1,
    CoderWorkerV1,
    MCPWorkerV1,
    ResearcherWorkerV1,
    VerifierWorkerV1,
)

from .clarification import ClarificationManager
from .enrichment import TurnEnricher
from .indexer import QAContextIndexer
from .models import (
    DialogueTurn,
    KernelResponse,
    QueryRequest,
    Stage1Result,
    Stage2Result,
    Stage2SubProblem,
    utc_now_iso,
)
from .store import SessionSQLiteStore

logger = logging.getLogger(__name__)


class QAContextKernel:
    def __init__(
        self,
        store: SessionSQLiteStore,
        indexer: QAContextIndexer,
        clarification: ClarificationManager,
        enricher: TurnEnricher,
        runner: SubagentRunner,
        plan_agent_v1: PlanAgentV1,
        dag_runner_v1: DAGRunnerV1,
        enable_plan_worker_v1: bool,
    ) -> None:
        self.store = store
        self.indexer = indexer
        self.clarification = clarification
        self.enricher = enricher
        self.runner = runner
        self.plan_agent_v1 = plan_agent_v1
        self.dag_runner_v1 = dag_runner_v1
        self.enable_plan_worker_v1 = enable_plan_worker_v1
        self._execution_snapshots: dict[str, dict[str, Any]] = {}
        self._execution_events: dict[str, list[dict[str, Any]]] = {}
        self._execution_requests: dict[str, dict[str, Any]] = {}

    @classmethod
    def create_default(cls, base_dir: str = "data/qa_v1/sessions") -> "QAContextKernel":
        store = SessionSQLiteStore(base_dir=base_dir)
        indexer = QAContextIndexer(store)
        clarification = ClarificationManager()
        enricher = TurnEnricher()
        registry = SubagentRegistry()
        registry.register(RetrievalSubagent())
        registry.register(ReasoningSubagent())
        registry.register(ResponseSubagent())
        runner = SubagentRunner(registry)

        worker_registry = WorkerRegistryV1()
        worker_registry.register(MCPWorkerV1())
        worker_registry.register(ResearcherWorkerV1())
        worker_registry.register(CoderWorkerV1())
        worker_registry.register(VerifierWorkerV1())
        worker_registry.register(AggregateWorkerV1())
        worker_router = WorkerRouterV1(worker_registry)

        plan_agent_v1 = PlanAgentV1()
        dag_runner_v1 = DAGRunnerV1(worker_router)
        enable_plan_worker_v1 = cls._env_flag("QA_PLAN_WORKER_V1_ENABLED", default=True)

        return cls(
            store=store,
            indexer=indexer,
            clarification=clarification,
            enricher=enricher,
            runner=runner,
            plan_agent_v1=plan_agent_v1,
            dag_runner_v1=dag_runner_v1,
            enable_plan_worker_v1=enable_plan_worker_v1,
        )

    async def handle_query(self, request: QueryRequest) -> KernelResponse:
        query = request.query.strip()
        if not query:
            raise ValueError("query is required")

        session_id = request.session_id or f"sess_{uuid.uuid4().hex[:12]}"
        trace_id = request.trace_id or f"trace_{uuid.uuid4().hex[:12]}"
        turn_id = f"turn_{uuid.uuid4().hex[:12]}"
        now = utc_now_iso()

        self._execution_requests[trace_id] = {
            "query": query,
            "session_id": session_id,
            "doc_scope": list(request.doc_scope),
            "options": dict(request.options),
        }
        logger.info(
            "qa_kernel_query_start",
            extra={
                "trace_id": trace_id,
                "session_id": session_id,
                "turn_id": turn_id,
                "query_len": len(query),
                "doc_scope_size": len(request.doc_scope),
                "plan_worker_v1_enabled": self.enable_plan_worker_v1,
            },
        )

        self.store.create_session(session_id=session_id, doc_scope=request.doc_scope)
        pending = DialogueTurn(
            turn_id=turn_id,
            session_id=session_id,
            created_at=now,
            updated_at=now,
            user_query=query,
            summary="pending",
            intent_tag="PENDING",
            trace_id=trace_id,
            status="pending",
        )
        self.store.append_turn(pending)

        stage1 = self._run_stage1(query=query, session_id=session_id, doc_scope=request.doc_scope)
        stage2 = self._run_stage2(query=query, stage1=stage1)
        logger.info(
            "qa_kernel_stage_analysis_done",
            extra={
                "trace_id": trace_id,
                "session_id": session_id,
                "turn_id": turn_id,
                "stage1_intent": stage1.coarse_intent,
                "stage1_confidence": stage1.confidence,
                "sub_problem_count": len(stage2.sub_problems),
                "clarification_needed": stage2.clarification_needed,
            },
        )
        await self._emit_execution_event(
            trace_id,
            {
                "type": "manager.parsed",
                "trace_id": trace_id,
                "turn_id": turn_id,
                "query": query,
                "stage1": stage1.to_dict(),
                "problems": self._extract_manager_problems(stage2.to_dict()),
            },
        )

        if self.clarification.should_clarify(stage2):
            thread = self.clarification.create_thread(
                session_id=session_id,
                turn_id=turn_id,
                query=query,
                stage2=stage2,
            )
            self.store.create_clarification(thread)
            self.store.update_turn(
                session_id=session_id,
                turn_id=turn_id,
                patch={
                    "status": "clarification_pending",
                    "intent_tag": stage1.coarse_intent,
                    "summary": self.enricher.build_summary(query, None),
                    "tags": ["qa-v1", "clarification"],
                    "stage1_result": stage1.to_dict(),
                    "stage2_result": stage2.to_dict(),
                    "clarification_thread_id": thread.thread_id,
                    "confidence": stage2.overall_confidence,
                },
            )
            return KernelResponse(
                status="clarification_pending",
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                intent_tag=stage1.coarse_intent,
                confidence=stage2.overall_confidence,
                stage1_result=stage1.to_dict(),
                stage2_result=stage2.to_dict(),
                clarification=thread.to_dict(),
            )

        selected_context = self.indexer.select_context(
            session_id=session_id,
            query=query,
            intent_hint=stage1.coarse_intent,
            limit=8,
        )
        logger.info(
            "qa_kernel_context_selected",
            extra={
                "trace_id": trace_id,
                "session_id": session_id,
                "turn_id": turn_id,
                "selected_context_count": len(selected_context),
            },
        )
        answer, agent_runs, citations, runner_confidence, routing_plan, execution_snapshot = await self._run_with_plan_worker_v1(
            request=request,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            query=query,
            stage1=stage1,
            stage2=stage2,
            selected_context=selected_context,
        )

        entities = self.enricher.extract_entities(query=query, answer=answer)
        tags, topic_tags = self.enricher.build_tags(
            intent_tag=stage1.coarse_intent,
            entities=entities,
            referenced_docs=request.doc_scope,
            stage2_result=stage2.to_dict(),
        )
        summary = self.enricher.build_summary(query=query, answer=answer)

        self.store.update_turn(
            session_id=session_id,
            turn_id=turn_id,
            patch={
                "assistant_answer": answer,
                "summary": summary,
                "tags": tags,
                "topic_tags": topic_tags,
                "intent_tag": stage1.coarse_intent,
                "entities": entities,
                "referenced_docs": request.doc_scope,
                "citations": citations,
                "stage1_result": stage1.to_dict(),
                "stage2_result": stage2.to_dict(),
                "routing_plan": routing_plan,
                "agent_runs": agent_runs,
                "confidence": min(0.99, round((stage1.confidence + runner_confidence) / 2.0, 4)),
                "status": "completed",
            },
        )

        execution_snapshot["summary"]["fallbackUsed"] = any(
            run.get("sub_problem_id") == "fallback_v0" for run in agent_runs
        )
        execution_snapshot["summary"]["finalStatus"] = "completed"
        execution_snapshot["summary"]["confidence"] = min(
            0.99, round((stage1.confidence + runner_confidence) / 2.0, 4)
        )
        self._execution_snapshots[trace_id] = execution_snapshot
        self._truncate_execution_cache()
        await self._emit_execution_event(
            trace_id,
            {
                "type": "final.ready",
                "trace_id": trace_id,
                "turn_id": turn_id,
                "answer_preview": answer[:220],
                "status": "complete",
                "progress": 100,
            },
        )
        logger.info(
            "qa_kernel_query_completed",
            extra={
                "trace_id": trace_id,
                "session_id": session_id,
                "turn_id": turn_id,
                "status": "completed",
                "confidence": execution_snapshot["summary"].get("confidence"),
                "fallback_used": execution_snapshot["summary"].get("fallbackUsed"),
                "citation_count": len(citations),
                "agent_run_count": len(agent_runs),
            },
        )

        return KernelResponse(
            status="completed",
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            answer=answer,
            summary=summary,
            tags=tags,
            intent_tag=stage1.coarse_intent,
            confidence=min(0.99, round((stage1.confidence + runner_confidence) / 2.0, 4)),
            citations=citations,
            stage1_result=stage1.to_dict(),
            stage2_result=stage2.to_dict(),
            execution=execution_snapshot,
        )

    async def _run_with_plan_worker_v1(
        self,
        request: QueryRequest,
        session_id: str,
        turn_id: str,
        trace_id: str,
        query: str,
        stage1: Stage1Result,
        stage2: Stage2Result,
        selected_context: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], float, list[dict[str, Any]], dict[str, Any]]:
        execution_snapshot = self._new_execution_snapshot(
            trace_id=trace_id,
            query=query,
            stage1=stage1.to_dict(),
            stage2=stage2.to_dict(),
        )
        if self.enable_plan_worker_v1:
            try:
                plan_request = PlanRequestV1(
                    query=query,
                    session_id=session_id,
                    turn_id=turn_id,
                    trace_id=trace_id,
                    doc_scope=request.doc_scope,
                    stage1_result=stage1.to_dict(),
                    stage2_result=stage2.to_dict(),
                    options=request.options,
                )
                plan = self.plan_agent_v1.build_plan(plan_request)
                logger.info(
                    "qa_kernel_plan_created",
                    extra={
                        "trace_id": trace_id,
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "plan_id": plan.plan_id,
                        "node_count": len(plan.nodes),
                    },
                )
                execution_snapshot["plan"] = {
                    "planId": plan.plan_id,
                    "metadata": plan.metadata,
                    "nodes": [node.to_dict() for node in plan.nodes],
                    "workers": self._build_worker_descriptors(plan.to_dict().get("nodes", [])),
                }
                await self._emit_execution_event(
                    trace_id,
                    {
                        "type": "plan.created",
                        "trace_id": trace_id,
                        "plan": execution_snapshot["plan"],
                    },
                )
                plan_result = await self.dag_runner_v1.run_plan(
                    request=plan_request,
                    plan=plan,
                    selected_context=selected_context,
                    event_callback=lambda event: self._emit_execution_event(trace_id, event),
                )
                if not plan_result.answer.strip():
                    raise ValueError("empty answer from plan/worker v1")
                execution_snapshot["workers"] = plan_result.node_runs
                logger.info(
                    "qa_kernel_plan_worker_v1_succeeded",
                    extra={
                        "trace_id": trace_id,
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "plan_id": plan.plan_id,
                        "confidence": plan_result.confidence,
                        "node_run_count": len(plan_result.node_runs),
                    },
                )
                return (
                    plan_result.answer,
                    plan_result.node_runs,
                    plan_result.citations,
                    plan_result.confidence,
                    plan.to_dict().get("nodes", []),
                    execution_snapshot,
                )
            except Exception as exc:
                logger.warning(
                    "qa_kernel_plan_worker_v1_failed_fallback_v0",
                    extra={
                        "trace_id": trace_id,
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "error": str(exc),
                    },
                )
                fallback_answer, fallback_runs, fallback_citations, fallback_confidence = await self.runner.run_plan(
                    session_id=session_id,
                    turn_id=turn_id,
                    trace_id=trace_id,
                    query=query,
                    sub_problems=[item.to_dict() for item in stage2.sub_problems],
                    selected_context=selected_context,
                )
                fallback_runs.append(
                    {
                        "sub_problem_id": "fallback_v0",
                        "capability": "fallback.runner.v0",
                        "agent": "SubagentRunner",
                        "success": True,
                        "error": str(exc),
                        "output": {"note": "fallback from plan/worker v1"},
                        "role": "FALLBACK",
                        "task_prompt": "Fallback to SubagentRunner V0 due to Plan/Worker V1 failure.",
                        "identity_prompt": "V0 compatibility fallback runner",
                        "progress": 100,
                    }
                )
                execution_snapshot["workers"] = fallback_runs
                execution_snapshot["summary"]["fallbackUsed"] = True
                await self._emit_execution_event(
                    trace_id,
                    {
                        "type": "fallback.started",
                        "trace_id": trace_id,
                        "error": str(exc),
                        "status": "running",
                        "progress": 85,
                    },
                )
                return (
                    fallback_answer,
                    fallback_runs,
                    fallback_citations,
                    fallback_confidence,
                    stage2.routing_plan,
                    execution_snapshot,
                )

        fallback_answer, fallback_runs, fallback_citations, fallback_confidence = await self.runner.run_plan(
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            query=query,
            sub_problems=[item.to_dict() for item in stage2.sub_problems],
            selected_context=selected_context,
        )
        execution_snapshot["workers"] = fallback_runs
        execution_snapshot["summary"]["fallbackUsed"] = True
        return (
            fallback_answer,
            fallback_runs,
            fallback_citations,
            fallback_confidence,
            stage2.routing_plan,
            execution_snapshot,
        )

    @staticmethod
    def _env_flag(name: str, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        normalized = value.strip().lower()
        return normalized not in {"0", "false", "off", "no"}

    async def handle_clarification(
        self,
        session_id: str,
        thread_id: str,
        answer: str,
    ) -> KernelResponse:
        thread = self.store.get_clarification(session_id=session_id, thread_id=thread_id)
        if thread is None:
            raise KeyError(f"clarification thread not found: {thread_id}")
        if thread.status != "pending":
            raise ValueError(f"clarification thread status is {thread.status}")

        refined_query = self.clarification.merge_clarification(thread.original_query, answer)
        self.store.resolve_clarification(
            session_id=session_id,
            thread_id=thread_id,
            answer=answer,
            resolved_query=refined_query,
        )
        return await self.handle_query(
            QueryRequest(
                query=refined_query,
                session_id=session_id,
            )
        )

    def list_turns(self, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return [turn.to_dict() for turn in self.store.list_turns(session_id=session_id, limit=limit)]

    def get_turn(self, session_id: str, turn_id: str) -> dict[str, Any] | None:
        turn = self.store.get_turn(session_id=session_id, turn_id=turn_id)
        return turn.to_dict() if turn else None

    def _run_stage1(self, query: str, session_id: str, doc_scope: list[str]) -> Stage1Result:
        query_lower = query.lower()
        if any(token in query_lower for token in ["你好", "hello", "hi", "hey"]):
            intent = "CHAT"
            confidence = 0.9
        elif len(query.strip()) <= 2 or query_lower in {"这个", "那个", "怎么弄"}:
            intent = "AMBIGUOUS"
            confidence = 0.45
        elif any(token in query_lower for token in ["对比", "比较", "分别", "同时", "并且", "以及"]):
            intent = "MULTI_PART"
            confidence = 0.78
        else:
            intent = "DOC_QA"
            confidence = 0.72

        contexts = self.indexer.select_context(
            session_id=session_id,
            query=query,
            intent_hint=None,
            limit=6,
        )
        reasoning = "context_match" if contexts else "no_context_match"
        return Stage1Result(
            coarse_intent=intent,
            confidence=confidence,
            relevant_context_ids=[str(item["turn_id"]) for item in contexts],
            selection_reasoning=reasoning,
            suggested_doc_scope=doc_scope,
            needs_refinement=intent == "AMBIGUOUS",
        )

    def _run_stage2(self, query: str, stage1: Stage1Result) -> Stage2Result:
        if stage1.needs_refinement:
            return Stage2Result(
                sub_problems=[],
                routing_plan=[],
                clarification_needed=True,
                clarification_question="你的问题还有歧义，请补充要查询的对象、目标和约束。",
                clarification_options=["补充对象", "补充期望结果", "补充文档范围"],
                overall_confidence=0.42,
            )

        segments = self._split_segments(query)
        sub_problems: list[Stage2SubProblem] = []
        routing_plan: list[dict[str, Any]] = []

        retrieval_ids: list[str] = []
        for idx, segment in enumerate(segments, start=1):
            node_id = f"sp_{idx}_retrieve"
            retrieval_ids.append(node_id)
            sub = Stage2SubProblem(
                sub_problem_id=node_id,
                question=segment,
                intent=stage1.coarse_intent,
                entities=[],
                route_type="context_retrieval",
                agent_capability="context.retrieve",
            )
            sub_problems.append(sub)
            routing_plan.append({
                "node": node_id,
                "capability": sub.agent_capability,
                "depends_on": [],
            })

        if len(segments) > 1:
            reason_id = "sp_reason"
            sub_problems.append(
                Stage2SubProblem(
                    sub_problem_id=reason_id,
                    question=query,
                    intent=stage1.coarse_intent,
                    entities=[],
                    route_type="reasoning",
                    agent_capability="reasoning.synthesize",
                    depends_on=retrieval_ids,
                    complexity="medium",
                )
            )
            routing_plan.append(
                {
                    "node": reason_id,
                    "capability": "reasoning.synthesize",
                    "depends_on": retrieval_ids,
                }
            )
            response_depends = [reason_id]
        else:
            response_depends = retrieval_ids

        response_id = "sp_response"
        sub_problems.append(
            Stage2SubProblem(
                sub_problem_id=response_id,
                question=query,
                intent=stage1.coarse_intent,
                entities=[],
                route_type="response",
                agent_capability="response.compose",
                depends_on=response_depends,
            )
        )
        routing_plan.append(
            {
                "node": response_id,
                "capability": "response.compose",
                "depends_on": response_depends,
            }
        )

        base_confidence = 0.75 if stage1.coarse_intent != "CHAT" else 0.88
        return Stage2Result(
            sub_problems=sub_problems,
            routing_plan=routing_plan,
            clarification_needed=False,
            overall_confidence=base_confidence,
        )

    def _split_segments(self, query: str) -> list[str]:
        normalized = query.strip()
        if len(normalized) <= 28:
            return [normalized]

        normalized = normalized.replace("以及", "|SPLIT|").replace("并且", "|SPLIT|")
        normalized = re.sub(r"[；;。？！!?]\s*", "|SPLIT|", normalized)
        normalized = re.sub(r"\s+和\s+", "|SPLIT|", normalized)

        parts = [part.strip() for part in normalized.split("|SPLIT|") if part.strip()]
        if not parts:
            return [query]

        deduped: list[str] = []
        seen: set[str] = set()
        for part in parts:
            key = re.sub(r"\W+", "", part.lower())[:100]
            if key in seen:
                continue
            seen.add(key)
            deduped.append(part)
        return deduped or [query]

    def get_execution_snapshot(self, trace_id: str) -> dict[str, Any] | None:
        snapshot = self._execution_snapshots.get(trace_id)
        if snapshot is None:
            return None
        return dict(snapshot)

    def get_execution_events(self, trace_id: str) -> list[dict[str, Any]]:
        return list(self._execution_events.get(trace_id, []))

    async def retry_execution(self, trace_id: str) -> KernelResponse:
        cached = self._execution_requests.get(trace_id)
        if cached is None:
            raise KeyError(f"execution request not found: {trace_id}")
        logger.info(
            "qa_kernel_retry_start",
            extra={
                "trace_id": trace_id,
                "session_id": cached.get("session_id"),
            },
        )
        return await self.handle_query(
            QueryRequest(
                query=str(cached.get("query") or ""),
                session_id=str(cached.get("session_id") or ""),
                doc_scope=list(cached.get("doc_scope") or []),
                options=dict(cached.get("options") or {}),
            )
        )

    def _new_execution_snapshot(
        self,
        trace_id: str,
        query: str,
        stage1: dict[str, Any],
        stage2: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "traceId": trace_id,
            "manager": {
                "query": query,
                "stage1": stage1,
                "problems": self._extract_manager_problems(stage2),
            },
            "plan": {
                "planId": "",
                "metadata": {},
                "nodes": [],
                "workers": [],
            },
            "workers": [],
            "summary": {
                "fallbackUsed": False,
                "finalStatus": "running",
                "confidence": 0.0,
            },
        }

    def _extract_manager_problems(self, stage2: dict[str, Any]) -> list[dict[str, Any]]:
        sub_problems = list(stage2.get("sub_problems") or [])
        problems: list[dict[str, Any]] = []
        for item in sub_problems:
            capability = str(item.get("agent_capability") or "")
            route_type = str(item.get("route_type") or "")
            if capability.startswith("response."):
                continue
            if capability.startswith("grounding.") or capability.startswith("aggregate."):
                continue
            if route_type == "response":
                continue
            problems.append(item)
        return problems

    def _build_worker_descriptors(self, plan_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        workers: dict[str, dict[str, Any]] = {}
        for node in plan_nodes:
            role = str(node.get("role") or "UNKNOWN")
            worker_id = f"worker-{role.lower()}"
            capability = str(node.get("capability") or "")
            entry = workers.setdefault(
                worker_id,
                {
                    "workerId": worker_id,
                    "role": role,
                    "identityPrompt": str(node.get("identity_prompt") or ""),
                    "capabilities": [],
                },
            )
            if capability and capability not in entry["capabilities"]:
                entry["capabilities"].append(capability)
        return list(workers.values())

    async def _emit_execution_event(self, trace_id: str, event: dict[str, Any]) -> None:
        payload = dict(event)
        payload.setdefault("trace_id", trace_id)
        payload.setdefault("timestamp", utc_now_iso())
        events = self._execution_events.setdefault(trace_id, [])
        payload.setdefault("seq", len(events) + 1)
        events.append(payload)
        self._truncate_execution_cache()
        await get_event_bus().publish(trace_id, payload)
        event_type = str(payload.get("type") or "")
        if event_type in {"manager.parsed", "plan.created", "fallback.started", "final.ready"}:
            logger.info(
                "qa_execution_event_emitted",
                extra={
                    "trace_id": trace_id,
                    "event_type": event_type,
                    "seq": payload.get("seq"),
                },
            )

    def _truncate_execution_cache(self) -> None:
        limit = 200
        if len(self._execution_snapshots) > limit:
            oldest = next(iter(self._execution_snapshots.keys()))
            self._execution_snapshots.pop(oldest, None)
        if len(self._execution_events) > limit:
            oldest = next(iter(self._execution_events.keys()))
            self._execution_events.pop(oldest, None)
        if len(self._execution_requests) > limit:
            oldest = next(iter(self._execution_requests.keys()))
            self._execution_requests.pop(oldest, None)
