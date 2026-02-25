"""PromptAgent v2 Implementation

入口控制层：路由决策 + 上下文治理
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from agent.core.types import (
    RouteType, ContextBlock, TraceContext
)

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
        
        # 2. 路由决策（简化版，实际应基于查询复杂度、歧义度等）
        route = self._determine_route(normalized_query, doc_id)
        
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
        # TODO: 实现更复杂的规范化（分词、去停用词等）
        return normalized
    
    def _determine_route(self, query: str, doc_id: Optional[str]) -> str:
        """确定路由类型
        
        简化逻辑：
        - 无 doc_id 且简单查询 -> FAST_PATH
        - 有 doc_id 且查询适中 -> DOC_GROUNDED
        - 复杂查询（多步骤、需要推理）-> MULTI_HOP
        """
        # 简单启发式：短查询走 FAST_PATH
        if len(query) < 20 and not doc_id:
            return RouteType.FAST_PATH
        
        # 需要检索文档的走 DOC_GROUNDED
        if doc_id:
            return RouteType.DOC_GROUNDED
        
        # 默认走 DOC_GROUNDED（假设大多数查询需要文档支持）
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
