"""WritingAgentV2 - 写作Agent

基于证据或常识生成用户问题的回答。

职责：
- FAST_PATH: 生成闲聊回复
- 无证据: 基于常识回答
- 有证据: 基于证据生成回答

继承自BaseAgent，享受统一生命周期管理。
同时保持 compose_answer 方法的向后兼容。
"""

import logging
from typing import TYPE_CHECKING, Dict, List

from agent.base import BaseAgent
from agent.registry import agent_registry

if TYPE_CHECKING:
    from agent.core.qa_context import QAContext

from agent.core.types import Citation, EvidencePack, RouteType
from agent.core.qa_prompts import WRITER_PROMPTS, NO_EVIDENCE_PROMPT, get_fallback_greeting
from agent.core.qa_llm import get_qa_llm

logger = logging.getLogger(__name__)


@agent_registry.register
class WritingAgentV2(BaseAgent):
    """写作Agent - 基于证据生成回答

    职责：
    - 接收 query, route, evidence_chunks
    - 调用LLM生成回答
    - 输出 answer, citations, confidence
    """

    @property
    def name(self) -> str:
        return "WritingAgentV2"

    @property
    def description(self) -> str:
        return "基于证据或常识生成回答"

    async def run(self, input_data: "QAContext") -> "QAContext":
        """执行写作任务

        Args:
            input_data: QAContext，必须包含 query, route, evidence_chunks

        Returns:
            QAContext，填充 answer, citations, confidence
        """
        logger.info(f"WritingAgentV2 处理 query: {input_data.query}, route: {input_data.route}")

        route = input_data.route
        chunks = input_data.evidence_chunks

        # FAST_PATH: 闲聊回复
        if route == RouteType.FAST_PATH:
            return await self._generate_fast_path(input_data)

        # 无证据: 基于常识回答
        if not chunks:
            return await self._generate_no_evidence(input_data)

        # 有证据: 基于证据回答
        return await self._generate_grounded(input_data)

    async def _generate_fast_path(self, ctx: "QAContext") -> "QAContext":
        """生成闲聊回复"""
        prompts = WRITER_PROMPTS[RouteType.FAST_PATH]

        try:
            llm_service = await get_qa_llm()

            if llm_service.is_available:
                user_prompt = prompts["user"].format(query=ctx.query)
                answer = await llm_service.chat(prompts["system"], user_prompt)

                ctx.answer = answer.strip() if answer else get_fallback_greeting(ctx.query)
                ctx.confidence = 0.7
                ctx.citations = []
            else:
                raise Exception("LLM不可用")

        except Exception as e:
            logger.warning(f"WritingAgent FAST_PATH LLM失败: {e}")
            ctx.answer = get_fallback_greeting(ctx.query)
            ctx.confidence = 0.5

        return ctx

    async def _generate_no_evidence(self, ctx: "QAContext") -> "QAContext":
        """无证据时生成回答"""
        try:
            llm_service = await get_qa_llm()

            if llm_service.is_available:
                user_prompt = NO_EVIDENCE_PROMPT["user"].format(query=ctx.query)
                answer = await llm_service.chat(NO_EVIDENCE_PROMPT["system"], user_prompt)

                ctx.answer = answer.strip() if answer else self._default_no_evidence(ctx.query)
                ctx.confidence = 0.5
                ctx.citations = []
            else:
                raise Exception("LLM不可用")

        except Exception as e:
            logger.warning(f"WritingAgent NO_EVIDENCE LLM失败: {e}")
            ctx.answer = self._default_no_evidence(ctx.query)
            ctx.confidence = 0.3

        return ctx

    async def _generate_grounded(self, ctx: "QAContext") -> "QAContext":
        """基于证据生成回答"""
        prompts = WRITER_PROMPTS[RouteType.DOC_GROUNDED]

        # 构建证据文本
        evidence_text = "\n\n".join([
            f"证据{i+1}: {chunk.get('text', '')[:200]}"
            for i, chunk in enumerate(ctx.evidence_chunks[:3])
        ])

        try:
            llm_service = await get_qa_llm()

            if llm_service.is_available:
                user_prompt = prompts["user"].format(
                    evidence=evidence_text,
                    query=ctx.query
                )
                answer = await llm_service.chat(prompts["system"], user_prompt)

                ctx.answer = answer.strip() if answer else evidence_text[:200]
                ctx.confidence = 0.8

                # 构建citations
                ctx.citations = [
                    Citation(
                        chunk_id=str(chunk.get("source") or f"chunk_{i+1}"),
                        text=str(chunk.get("text", ""))[:200],
                        score=float(chunk.get("score", 0.0))
                    )
                    for i, chunk in enumerate(ctx.evidence_chunks[:3])
                ]
            else:
                raise Exception("LLM不可用")

        except Exception as e:
            logger.warning(f"WritingAgent GROUNDED LLM失败: {e}")
            # 降级到直接拼接证据
            ctx.answer = f"基于检索到的证据：\n{evidence_text[:300]}"
            ctx.confidence = 0.6
            ctx.citations = [
                Citation(
                    chunk_id=str(chunk.get("source") or f"chunk_{i+1}"),
                    text=str(chunk.get("text", ""))[:200],
                    score=float(chunk.get("score", 0.0))
                )
                for i, chunk in enumerate(ctx.evidence_chunks[:3])
            ]

        return ctx

    def _default_no_evidence(self, query: str) -> str:
        """无证据时的默认回复"""
        return f"抱歉，我目前没有关于「{query}」的相关信息。能否换个问题，或者提供更多背景？"

    # ========== 向后兼容接口 ==========

    async def compose_answer(self, query: str, route: RouteType, evidence: EvidencePack) -> Dict[str, object]:
        """向后兼容的接口

        供后端API直接调用，保持与旧代码的兼容性。

        Args:
            query: 用户查询
            route: 路由类型
            evidence: 证据包

        Returns:
            {"answer": str, "citations": List[Citation], "confidence": float}
        """
        # 转换evidence为QAContext格式
        from agent.core.qa_context import QAContext

        ctx = QAContext(
            query=query,
            route=route,
            evidence_chunks=evidence.chunks
        )

        # 执行写作
        result_ctx = await self.run(ctx)

        return {
            "answer": result_ctx.answer,
            "citations": result_ctx.citations,
            "confidence": result_ctx.confidence
        }