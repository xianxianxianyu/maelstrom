"""PromptAgent v2 Implementation

入口控制层：输入规范化 + 上下文治理

职责：
- 输入规范化、去重、压缩
- 路由决策（调用RouterAgent或使用LLM）
- 输出 context_blocks 结构化上下文
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from agent.core.types import (
    RouteType, ContextBlock, TraceContext
)
from agent.core.qa_prompts import ROUTER_PROMPTS, get_fallback_greeting
from agent.core.qa_llm import get_qa_llm

logger = logging.getLogger(__name__)


class PromptAgentV2:
    """PromptAgent v2 - 入口控制层
    
    职责：
    - 输入规范化、去重、压缩
    - 路由决策：FAST_PATH / DOC_GROUNDED / MULTI_HOP
    - 输出 context_blocks 结构化上下文
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__ + ".PromptAgentV2")
    
    async def process(
        self,
        query: str,
        doc_id: Optional[str] = None,
        trace_ctx: Optional[TraceContext] = None
    ) -> Dict[str, Any]:
        """处理请求，输出路由决策和上下文块

        Args:
            query: 用户查询
            doc_id: 文档ID（可选）
            trace_ctx: 追踪上下文（可选）

        Returns:
            包含 route, context_blocks, confidence 的字典
        """
        if trace_ctx:
            trace_ctx.log_event("prompt_agent_start", {"query": query, "doc_id": doc_id})

        # 1. 输入规范化
        normalized_query = self._normalize_query(query)

        # 2. 路由决策（AI判断）
        route = await self._determine_route(normalized_query, doc_id)

        # 记录路由决策详情
        if trace_ctx:
            trace_ctx.log_event("router_decision", {
                "query": query,
                "normalized_query": normalized_query,
                "route": route,
                "doc_id": doc_id,
                "query_length": len(query)
            })

        # 3. 构建 context_blocks
        context_blocks = self._build_context_blocks(normalized_query, doc_id, route)

        # 4. 计算置信度
        confidence = self._calculate_confidence(route, context_blocks)

        result = {
            "route": route,
            "context_blocks": context_blocks,
            "confidence": confidence,
            "normalized_query": normalized_query
        }

        if trace_ctx:
            trace_ctx.log_event("prompt_agent_end", result)

        self.logger.info(f"PromptAgent processed query: route={route}, confidence={confidence:.2f}")
        return result
    
    def _normalize_query(self, query: str) -> str:
        """查询规范化：去除多余空格、统一大小写等"""
        normalized = query.strip()
        return normalized

    async def _determine_route(self, query: str, doc_id: Optional[str]) -> str:
        """用AI确定路由类型

        调用LLM判断用户问题应该使用哪种路由：
        - FAST_PATH: 闲聊、问候、确认等
        - DOC_GROUNDED: 需要检索知识库的问题
        - MULTI_HOP: 复杂多步推理问题
        """
        # 有指定doc_id，必须走DOC_GROUNDED
        if doc_id:
            return RouteType.DOC_GROUNDED

        try:
            llm_service = await get_qa_llm()

            if llm_service.is_available:
                # 调用AI判断路由
                user_prompt = ROUTER_PROMPTS["user"].format(query=query)
                result = await llm_service.chat(ROUTER_PROMPTS["system"], user_prompt)
                result = result.strip().upper()

                # 解析AI返回的路由
                if "FAST_PATH" in result:
                    return RouteType.FAST_PATH
                elif "MULTI_HOP" in result:
                    return RouteType.MULTI_HOP
                elif "DOC_GROUNDED" in result:
                    return RouteType.DOC_GROUNDED

        except Exception as e:
            logger.warning(f"AI路由判断失败，使用默认逻辑: {e}")

        # AI调用失败时的备用逻辑
        return self._fallback_route_decision(query)

    def _fallback_route_decision(self, query: str) -> str:
        """备用路由决策（规则-based）"""
        greeting_keywords = ["你好", "hello", "hi", "您好", "嗨", "hey"]
        query_lower = query.lower().strip()
        if any(kw in query_lower for kw in greeting_keywords):
            return RouteType.FAST_PATH

        confirmation_patterns = ["谢谢", "知道了", "明白", "好的", "ok", "okay", "再见"]
        if any(p in query_lower for p in confirmation_patterns):
            return RouteType.FAST_PATH

        # 默认走DOC_GROUNDED
        return RouteType.DOC_GROUNDED
    
    def _build_context_blocks(
        self,
        query: str,
        doc_id: Optional[str],
        route: str
    ) -> List[Dict[str, Any]]:
        """构建上下文块
        
        现在只是骨架，实际应该：
        - FAST_PATH: 返回空或简单上下文
        - DOC_GROUNDED: 检索文档 chunks
        - MULTI_HOP: 构建多跳检索计划
        """
        blocks = []
        
        # 基础上下文块：查询信息
        blocks.append({
            "type": "query_info",
            "data": {
                "original_query": query,
                "route": route,
                "timestamp": datetime.utcnow().isoformat()
            }
        })
        
        # 如果有 doc_id，添加文档上下文块（实际应该检索 chunks）
        if doc_id:
            blocks.append({
                "type": "doc_context",
                "data": {
                    "doc_id": doc_id,
                    "status": "pending_retrieval",  # 实际应该检索后更新
                    "chunks": []  # 实际应该填充检索到的 chunks
                }
            })
        
        return blocks
    
    def _calculate_confidence(self, route: str, context_blocks: List[Dict]) -> float:
        """计算置信度（简化版）"""
        # 基础置信度
        base_confidence = 0.7
        
        # 根据路由调整
        if route == RouteType.FAST_PATH:
            base_confidence += 0.1  # 简单查询置信度稍高
        elif route == RouteType.MULTI_HOP:
            base_confidence -= 0.1  # 复杂查询初始置信度稍低
        
        # 根据上下文块数量微调
        if len(context_blocks) > 2:
            base_confidence += 0.05
        
        return min(0.95, max(0.5, base_confidence))
