import pytest

from agent.qa_context_v1.kernel import QAContextKernel
from agent.qa_context_v1.models import QueryRequest
from agent.qa_orchestration.contracts_v1 import PlanRequestV1, WorkerRole
from agent.qa_orchestration.dag_runner_v1 import DAGRunnerV1
from agent.qa_orchestration.plan_agent_v1 import PlanAgentV1
from agent.qa_orchestration.worker_registry_v1 import WorkerRegistryV1
from agent.qa_orchestration.worker_router_v1 import WorkerRouterV1
from agent.qa_orchestration.workers import (
    AggregateWorkerV1,
    CoderWorkerV1,
    MCPWorkerV1,
    ResearcherWorkerV1,
    VerifierWorkerV1,
)


def _build_runner() -> DAGRunnerV1:
    registry = WorkerRegistryV1()
    registry.register(MCPWorkerV1())
    registry.register(ResearcherWorkerV1())
    registry.register(CoderWorkerV1())
    registry.register(VerifierWorkerV1())
    registry.register(AggregateWorkerV1())
    return DAGRunnerV1(WorkerRouterV1(registry))


def _sample_plan_request() -> PlanRequestV1:
    return PlanRequestV1(
        query="解释文档结论",
        session_id="s1",
        turn_id="t1",
        trace_id="tr1",
        doc_scope=["doc-1"],
        stage1_result={"coarse_intent": "DOC_QA", "confidence": 0.9},
        stage2_result={
            "sub_problems": [
                {
                    "sub_problem_id": "sp1",
                    "question": "检索相关上下文",
                    "intent": "retrieve",
                    "entities": [],
                    "route_type": "context_retrieval",
                    "agent_capability": "context.retrieve",
                    "tools": ["context-index"],
                    "depends_on": [],
                },
                {
                    "sub_problem_id": "sp2",
                    "question": "生成回答",
                    "intent": "response",
                    "entities": [],
                    "route_type": "response",
                    "agent_capability": "response.compose",
                    "tools": [],
                    "depends_on": ["sp1"],
                },
            ],
            "routing_plan": [
                {"sub_problem_id": "sp1", "capability": "context.retrieve", "depends_on": []},
                {"sub_problem_id": "sp2", "capability": "response.compose", "depends_on": ["sp1"]},
            ],
            "clarification_needed": False,
            "overall_confidence": 0.8,
        },
        options={"timeout_ms": 3000, "max_context_chars": 3000},
    )


def test_plan_agent_v1_builds_verifier_node() -> None:
    plan_agent = PlanAgentV1()
    plan = plan_agent.build_plan(_sample_plan_request())

    assert plan.nodes
    assert plan.nodes[-1].capability == "grounding.verify"
    assert plan.nodes[-1].role == WorkerRole.VERIFIER
    assert any(node.role == WorkerRole.RESEARCHER for node in plan.nodes)
    assert any(node.role == WorkerRole.CODER for node in plan.nodes)


@pytest.mark.asyncio
async def test_dag_runner_v1_executes_plan_with_verification() -> None:
    request = _sample_plan_request()
    plan = PlanAgentV1().build_plan(request)
    runner = _build_runner()

    selected_context = [
        {
            "turn_id": "turn_001",
            "summary": "文档指出方法 A 在准确率上优于方法 B。",
            "score": 0.92,
        }
    ]
    result = await runner.run_plan(request=request, plan=plan, selected_context=selected_context)

    assert result.answer
    assert result.confidence > 0
    assert len(result.node_runs) >= 2
    assert any(run["capability"] == "grounding.verify" and run["success"] for run in result.node_runs)


@pytest.mark.asyncio
async def test_kernel_fallback_to_v0_when_plan_v1_fails(tmp_path) -> None:
    kernel = QAContextKernel.create_default(base_dir=str(tmp_path / "sessions"))

    def _raise_plan_error(_request: PlanRequestV1):
        raise RuntimeError("forced plan error")

    kernel.plan_agent_v1.build_plan = _raise_plan_error  # type: ignore[method-assign]

    response = await kernel.handle_query(QueryRequest(query="请总结这篇文档", session_id="session-fallback"))

    assert response.status == "completed"
    assert response.answer

    turn = kernel.store.get_turn("session-fallback", response.turn_id)
    assert turn is not None
    assert any(run.get("sub_problem_id") == "fallback_v0" for run in turn.agent_runs)
