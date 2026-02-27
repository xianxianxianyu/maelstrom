from __future__ import annotations

import uuid
from typing import Any

from agent.qa_orchestration.subagent_registry import SubagentRegistry
from agent.qa_orchestration.subagent_runner import (
    ReasoningSubagent,
    ResponseSubagent,
    RetrievalSubagent,
    SubagentRunner,
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


class QAContextKernel:
    def __init__(
        self,
        store: SessionSQLiteStore,
        indexer: QAContextIndexer,
        clarification: ClarificationManager,
        enricher: TurnEnricher,
        runner: SubagentRunner,
    ) -> None:
        self.store = store
        self.indexer = indexer
        self.clarification = clarification
        self.enricher = enricher
        self.runner = runner

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
        return cls(store=store, indexer=indexer, clarification=clarification, enricher=enricher, runner=runner)

    async def handle_query(self, request: QueryRequest) -> KernelResponse:
        query = request.query.strip()
        if not query:
            raise ValueError("query is required")

        session_id = request.session_id or f"sess_{uuid.uuid4().hex[:12]}"
        trace_id = f"trace_{uuid.uuid4().hex[:12]}"
        turn_id = f"turn_{uuid.uuid4().hex[:12]}"
        now = utc_now_iso()

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
        answer, agent_runs, citations, runner_confidence = await self.runner.run_plan(
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            query=query,
            sub_problems=[item.to_dict() for item in stage2.sub_problems],
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
                "routing_plan": stage2.routing_plan,
                "agent_runs": agent_runs,
                "confidence": min(0.99, round((stage1.confidence + runner_confidence) / 2.0, 4)),
                "status": "completed",
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
            stage1_result=stage1.to_dict(),
            stage2_result=stage2.to_dict(),
        )

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
        normalized = query.replace("以及", "和").replace("并且", "和")
        parts = [part.strip() for part in normalized.split("和") if part.strip()]
        return parts or [query]
