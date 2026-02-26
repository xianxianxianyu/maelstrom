import pytest

from agent.agents.plan_agent_v2 import PlanAgentV2
from agent.agents.prompt_agent_v2 import PromptAgentV2
from agent.agents.verifier_agent_v2 import VerifierAgentV2
from agent.agents.writing_agent_v2 import WritingAgentV2
from agent.core.types import EvidencePack, RouteType


@pytest.mark.asyncio
async def test_prompt_agent_routes_doc_grounded_when_doc_id_present() -> None:
    agent = PromptAgentV2()
    result = await agent.process("请解释这篇论文的方法", doc_id="doc_1")

    assert result["route"] == RouteType.DOC_GROUNDED.value
    assert result["normalized_query"] == "请解释这篇论文的方法"


@pytest.mark.asyncio
async def test_plan_agent_multi_hop_contains_reason_node() -> None:
    agent = PlanAgentV2()
    plan = await agent.build_plan("对比两种方法优劣", RouteType.MULTI_HOP, doc_id="doc_1")

    node_ids = [node.node_id for node in plan.nodes]
    assert "retrieve_primary" in node_ids
    assert "retrieve_secondary" in node_ids
    assert "reason" in node_ids
    assert "write" in node_ids
    assert "verify" in node_ids


@pytest.mark.asyncio
async def test_writing_agent_returns_citations_with_evidence() -> None:
    agent = WritingAgentV2()
    evidence = EvidencePack(
        chunks=[
            {"text": "第一条证据内容", "source": "chunk_1", "score": 0.8},
            {"text": "第二条证据内容", "source": "chunk_2", "score": 0.7},
        ]
    )

    result = await agent.compose_answer("总结关键结论", RouteType.DOC_GROUNDED, evidence)

    assert result["answer"]
    assert len(result["citations"]) >= 1
    assert 0.0 <= result["confidence"] <= 1.0


@pytest.mark.asyncio
async def test_verifier_requires_citations_on_grounded_route() -> None:
    agent = VerifierAgentV2()
    result = await agent.verify(
        route=RouteType.DOC_GROUNDED,
        answer="这是一个回答",
        citations=[],
        evidence=EvidencePack(chunks=[]),
    )

    assert result["passed"] is False
    assert any("citation" in reason for reason in result["reasons"])
