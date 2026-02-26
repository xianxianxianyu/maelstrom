"""RouterAgent - 路由决策Agent

负责判断用户问题应使用哪种处理方式：
- FAST_PATH: 闲聊、问候、确认等
- DOC_GROUNDED: 需要检索知识库
- MULTI_HOP: 复杂多步推理

继承自BaseAgent，享受统一生命周期管理。
"""

import logging
from typing import TYPE_CHECKING

from agent.base import BaseAgent
from agent.registry import agent_registry

if TYPE_CHECKING:
    from agent.core.qa_context import QAContext

from agent.core.qa_prompts import ROUTER_PROMPTS
from agent.core.qa_llm import get_qa_llm
from agent.core.types import RouteType

logger = logging.getLogger(__name__)


@agent_registry.register
class RouterAgent(BaseAgent):
    """路由决策Agent

    职责：
    - 接收用户query和doc_id
    - 调用LLM判断路由类型
    - 输出route、confidence、reasoning
    """

    @property
    def name(self) -> str:
        return "RouterAgent"

    @property
    def description(self) -> str:
        return "负责判断用户问题应使用哪种路由策略（FAST_PATH/DOC_GROUNDED/MULTI_HOP）"

    async def run(self, input_data: "QAContext") -> "QAContext":
        """执行路由决策

        Args:
            input_data: QAContext，必须包含 query

        Returns:
            QAContext，填充 route, route_confidence, route_reasoning
        """
        logger.info(f"RouterAgent 处理 query: {input_data.query}")

        # 有指定doc_id，必须走DOC_GROUNDED
        if input_data.doc_id:
            input_data.route = RouteType.DOC_GROUNDED
            input_data.route_confidence = 1.0
            input_data.route_reasoning = "指定了文档ID，必须检索该文档"
            return input_data

        try:
            llm_service = await get_qa_llm()

            if not llm_service.is_available:
                logger.warning("LLM不可用，使用规则降级")
                return self._fallback_decision(input_data)

            # 构建prompt
            user_prompt = ROUTER_PROMPTS["user"].format(query=input_data.query)

            # 调用LLM
            result = await llm_service.chat(ROUTER_PROMPTS["system"], user_prompt)
            result = result.strip().upper()

            # 解析路由
            if "FAST_PATH" in result:
                input_data.route = RouteType.FAST_PATH
            elif "MULTI_HOP" in result:
                input_data.route = RouteType.MULTI_HOP
            else:
                # 默认走DOC_GROUNDED
                input_data.route = RouteType.DOC_GROUNDED

            input_data.route_confidence = 0.8
            input_data.route_reasoning = result

            logger.info(f"RouterAgent 决策: {input_data.route.value}")

        except Exception as e:
            logger.warning(f"RouterAgent LLM调用失败: {e}")
            return self._fallback_decision(input_data, error=str(e))

        return input_data

    def _fallback_decision(self, input_data: "QAContext", error: str = "") -> "QAContext":
        """规则降级决策

        LLM调用失败时的备用逻辑：
        - 闲聊关键词 -> FAST_PATH
        - 其他 -> DOC_GROUNDED
        """
        greetings = ["你好", "hello", "hi", "您好", "嗨", "hey"]
        query_lower = input_data.query.lower().strip()

        if any(g in query_lower for g in greetings):
            input_data.route = RouteType.FAST_PATH
            input_data.route_confidence = 0.5
            input_data.route_reasoning = f"LLM调用失败，使用规则降级: {error}" if error else "规则降级"
        else:
            input_data.route = RouteType.DOC_GROUNDED
            input_data.route_confidence = 0.5
            input_data.route_reasoning = f"LLM调用失败，使用规则降级: {error}" if error else "规则降级"

        return input_data