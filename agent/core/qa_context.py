"""QA Pipeline 专用 Context

定义 QA Pipeline 中各 Agent 间共享的上下文数据结构，
与翻译工作流的 AgentContext 分离，保持 QA 模块独立性。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, List, TYPE_CHECKING

from agent.core.types import RouteType, TraceContext

if TYPE_CHECKING:
    from agent.core.types import Citation


@dataclass
class QAContext:
    """QA Pipeline 中各 Agent 间共享的上下文

    数据流：
    1. PromptAgent 填充 query, doc_id, session_id
    2. RouterAgent 填充 route, route_confidence, route_reasoning
    3. Retrieve 节点填充 evidence_chunks
    4. WritingAgent 填充 answer, citations, confidence

    Attributes:
        query: 用户查询
        doc_id: 指定的文档ID（可选）
        session_id: 会话ID
        route: 路由类型
        route_confidence: 路由决策置信度
        route_reasoning: 路由决策理由
        evidence_chunks: 检索到的证据片段
        answer: 生成的回答
        citations: 引用列表
        confidence: 回答置信度
        trace_ctx: 追踪上下文
        error: 错误信息
    """

    # 输入
    query: str = ""
    doc_id: Optional[str] = None
    session_id: str = "default"

    # 路由决策（RouterAgent产出）
    route: Optional[RouteType] = None
    route_confidence: float = 0.0
    route_reasoning: str = ""

    # 检索结果（Retrieve节点产出）
    evidence_chunks: List[Dict[str, Any]] = field(default_factory=list)

    # 生成结果（WritingAgent产出）
    answer: str = ""
    citations: List[Any] = field(default_factory=list)
    confidence: float = 0.0

    # 追踪与状态
    trace_ctx: Optional[TraceContext] = None
    error: Optional[str] = None

    def is_valid(self) -> bool:
        """检查上下文是否有效"""
        return bool(self.query and self.route)

    def has_evidence(self) -> bool:
        """是否有证据"""
        return bool(self.evidence_chunks)

    def to_dict(self) -> dict:
        """转换为字典（用于日志/响应）"""
        return {
            "query": self.query,
            "doc_id": self.doc_id,
            "session_id": self.session_id,
            "route": self.route.value if self.route else None,
            "route_confidence": self.route_confidence,
            "answer": self.answer,
            "confidence": self.confidence,
            "citation_count": len(self.citations),
            "has_evidence": self.has_evidence(),
            "error": self.error,
        }