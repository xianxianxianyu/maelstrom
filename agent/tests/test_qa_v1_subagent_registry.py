import asyncio

from agent.qa_orchestration.subagent_registry import SubagentRegistry
from agent.qa_orchestration.subagent_runner import (
    ReasoningSubagent,
    ResponseSubagent,
    RetrievalSubagent,
    SubagentRunner,
)


def test_registry_resolves_capabilities():
    registry = SubagentRegistry()
    registry.register(RetrievalSubagent())
    registry.register(ReasoningSubagent())
    registry.register(ResponseSubagent())

    retrieval = registry.resolve("context.retrieve")
    responder = registry.resolve("response.compose")

    assert retrieval.name == "retrieval-subagent"
    assert responder.name == "response-subagent"


def test_runner_executes_simple_plan():
    registry = SubagentRegistry()
    registry.register(RetrievalSubagent())
    registry.register(ResponseSubagent())
    runner = SubagentRunner(registry)

    sub_problems = [
        {
            "sub_problem_id": "p1",
            "question": "检索上下文",
            "agent_capability": "context.retrieve",
            "depends_on": [],
        },
        {
            "sub_problem_id": "p2",
            "question": "产出回复",
            "agent_capability": "response.compose",
            "depends_on": ["p1"],
        },
    ]
    selected_context = [{"turn_id": "t1", "summary": "历史记录", "score": 0.8}]

    answer, runs, citations, confidence = asyncio.run(
        runner.run_plan(
            session_id="s-runner",
            turn_id="turn-1",
            trace_id="trace-1",
            query="测试",
            sub_problems=sub_problems,
            selected_context=selected_context,
        )
    )

    assert answer
    assert len(runs) == 2
    assert citations
    assert 0.0 <= confidence <= 1.0
