"""QAAgent — RAG 增强的智能问答 Agent

基于文档的多轮对话问答 Agent：
- 使用 DocSearchTool 检索相关文档片段
- ConversationHistory 管理多轮对话（最近 20 轮）
- 构建带上下文和历史的 prompt
- 返回带引用来源的回答
- 支持 doc_id 切换检索范围
- 低相关度阈值检测

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agent.base import BaseAgent
from agent.registry import agent_registry
from agent.tools.base import ToolResult
from agent.tools.doc_search_tool import DocSearchTool

logger = logging.getLogger(__name__)

# Default relevance threshold — chunks below this score are considered irrelevant
DEFAULT_RELEVANCE_THRESHOLD = 0.3

# Default number of top chunks to retrieve
DEFAULT_TOP_K = 5

# System prompt template for QA
_QA_SYSTEM_PROMPT = """\
你是一个学术论文问答助手。请根据提供的文档片段和对话历史，准确回答用户的问题。

规则：
1. 仅基于提供的文档片段回答问题，不要编造信息。
2. 如果文档片段中没有相关信息，请明确告知用户。
3. 回答时请标注引用来源。
4. 保持回答简洁、准确、学术化。"""

# Low-relevance response message
_LOW_RELEVANCE_MESSAGE = (
    "当前文档中未找到与您问题相关的内容。建议您：\n"
    "1. 尝试改写问题，使用更具体的术语\n"
    "2. 确认当前文档是否包含相关主题"
)


# ---------------------------------------------------------------------------
# ConversationHistory
# ---------------------------------------------------------------------------


@dataclass
class ConversationHistory:
    """QA Agent 对话历史

    维护单个会话的对话消息列表，自动截断到最近 max_turns 轮。
    每轮包含一条 user 消息和一条 assistant 消息，因此最大消息数为
    max_turns * 2。

    Attributes:
        session_id: 会话唯一标识
        messages: 消息列表，每条消息为 {"role": "user"|"assistant", "content": str}
        max_turns: 最大对话轮数（默认 20）
        doc_id: 当前关联的文档 ID（可选）
    """

    session_id: str
    messages: list[dict] = field(default_factory=list)
    max_turns: int = 20
    doc_id: str | None = None

    def add(self, role: str, content: str) -> None:
        """添加一条消息并自动截断

        Args:
            role: 消息角色，"user" 或 "assistant"
            content: 消息内容
        """
        self.messages.append({"role": role, "content": content})
        # 保留最近 max_turns 轮（每轮 2 条消息）
        max_messages = self.max_turns * 2
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]

    def get_context_messages(self) -> list[dict]:
        """获取对话历史消息的副本

        Returns:
            消息列表的浅拷贝
        """
        return list(self.messages)


# ---------------------------------------------------------------------------
# QAAgent
# ---------------------------------------------------------------------------


@agent_registry.register
class QAAgent(BaseAgent):
    """RAG 智能问答 Agent：基于文档的多轮对话

    使用 DocSearchTool 检索相关文档片段，结合对话历史和 LLM 生成回答。
    支持按 doc_id 隔离检索范围，支持多会话管理。

    Attributes:
        _doc_search_tool: 文档检索工具实例
        _translation_service: 翻译服务实例（用于 LLM 调用）
        _sessions: 会话历史字典 {session_id: ConversationHistory}
        _relevance_threshold: 相关度阈值
    """

    def __init__(
        self,
        doc_search_tool: DocSearchTool | None = None,
        translation_service: Any | None = None,
        relevance_threshold: float = DEFAULT_RELEVANCE_THRESHOLD,
    ) -> None:
        """初始化 QAAgent

        Args:
            doc_search_tool: 可选的 DocSearchTool 实例（依赖注入）
            translation_service: 可选的 TranslationService 实例（依赖注入，
                                 用于测试时避免调用真实 LLM）
            relevance_threshold: 相关度阈值，低于此值的检索结果视为不相关
        """
        self._doc_search_tool = doc_search_tool or DocSearchTool()
        self._translation_service = translation_service
        self._sessions: dict[str, ConversationHistory] = {}
        self._relevance_threshold = relevance_threshold

    @property
    def name(self) -> str:
        return "qa"

    @property
    def description(self) -> str:
        return "RAG 智能问答 Agent：基于文档的多轮对话"

    async def _get_translation_service(self) -> Any:
        """获取或创建 TranslationService 实例（延迟初始化）

        Returns:
            TranslationService 实例
        """
        if self._translation_service is None:
            from backend.app.services.translator import TranslationService

            self._translation_service = await TranslationService.from_manager()
        return self._translation_service

    async def run(self, input_data: Any, **kwargs) -> dict:
        """执行问答

        Args:
            input_data: 输入字典，包含：
                - question (str, 必需): 用户问题
                - session_id (str, 可选): 会话 ID，默认 "default"
                - doc_id (str, 可选): 文档 ID，限制检索范围

        Returns:
            dict: {
                "answer": str,          # 回答文本
                "citations": list[dict]  # 引用来源列表
            }

        Raises:
            ValueError: 当 input_data 不是字典或缺少 question 字段时
        """
        if not isinstance(input_data, dict):
            raise ValueError(
                f"input_data must be a dict, got {type(input_data).__name__}"
            )

        question = input_data.get("question")
        if not question or not isinstance(question, str) or not question.strip():
            raise ValueError("Missing or empty required field: question")

        session_id = input_data.get("session_id", "default")
        doc_id = input_data.get("doc_id")

        # 1. 检索相关文档片段
        chunks = await self._search_docs(question, doc_id)

        # 2. 获取对话历史（处理 doc_id 切换）
        history = self._get_history(session_id, doc_id)

        # 3. 检查相关度阈值
        relevant_chunks = [
            c for c in chunks if c.get("score", 0) >= self._relevance_threshold
        ]

        if not relevant_chunks and chunks:
            # 所有检索结果相关度均低于阈值
            answer = _LOW_RELEVANCE_MESSAGE
            self._update_history(session_id, question, answer)
            return {
                "answer": answer,
                "citations": [],
            }

        # 4. 构建带上下文的 prompt
        context = self._build_context(relevant_chunks, history)

        # 5. 调用 LLM 生成回答
        answer = await self._generate_answer(question, context)

        # 6. 更新对话历史
        self._update_history(session_id, question, answer)

        # 7. 返回带引用的回答
        return {
            "answer": answer,
            "citations": [
                {"text": c["text"], "source": c["source"]}
                for c in relevant_chunks
            ],
        }

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    async def _search_docs(
        self, question: str, doc_id: str | None = None
    ) -> list[dict]:
        """使用 DocSearchTool 检索相关文档片段

        Args:
            question: 用户问题
            doc_id: 可选的文档 ID，限制检索范围

        Returns:
            检索结果列表，每项包含 text、source、score
        """
        search_kwargs: dict[str, Any] = {
            "action": "search",
            "query": question,
            "top_k": DEFAULT_TOP_K,
        }
        if doc_id is not None:
            search_kwargs["doc_id"] = doc_id

        result: ToolResult = await self._doc_search_tool.execute(**search_kwargs)

        if not result.success:
            logger.warning("DocSearch failed: %s", result.error)
            return []

        chunks = result.data.get("chunks", []) if result.data else []
        logger.info(
            "Retrieved %d chunks for question '%s' (doc_id=%s)",
            len(chunks),
            question[:50],
            doc_id or "all",
        )
        return chunks

    def _get_history(
        self, session_id: str, doc_id: str | None = None
    ) -> ConversationHistory:
        """获取或创建会话历史

        当 doc_id 变化时，更新检索范围但保留对话历史（Req 4.5）。

        Args:
            session_id: 会话 ID
            doc_id: 当前文档 ID

        Returns:
            ConversationHistory 实例
        """
        if session_id not in self._sessions:
            self._sessions[session_id] = ConversationHistory(
                session_id=session_id,
                doc_id=doc_id,
            )
        else:
            # 切换文档时更新 doc_id，保留对话历史 (Req 4.5)
            if doc_id is not None:
                self._sessions[session_id].doc_id = doc_id

        return self._sessions[session_id]

    def _build_context(
        self,
        chunks: list[dict],
        history: ConversationHistory,
    ) -> str:
        """构建带文档片段和对话历史的上下文

        Args:
            chunks: 检索到的文档片段列表
            history: 对话历史

        Returns:
            格式化的上下文字符串
        """
        parts: list[str] = []

        # 添加文档片段上下文
        if chunks:
            parts.append("=== 相关文档片段 ===")
            for i, chunk in enumerate(chunks, 1):
                source = chunk.get("source", "未知来源")
                text = chunk.get("text", "")
                parts.append(f"[片段 {i}] 来源: {source}")
                parts.append(text)
                parts.append("")

        # 添加对话历史
        history_messages = history.get_context_messages()
        if history_messages:
            parts.append("=== 对话历史 ===")
            for msg in history_messages:
                role_label = "用户" if msg["role"] == "user" else "助手"
                parts.append(f"{role_label}: {msg['content']}")
            parts.append("")

        return "\n".join(parts)

    async def _generate_answer(self, question: str, context: str) -> str:
        """调用 LLM 生成回答

        Args:
            question: 用户问题
            context: 构建的上下文（包含文档片段和对话历史）

        Returns:
            LLM 生成的回答文本
        """
        svc = await self._get_translation_service()

        system_prompt = _QA_SYSTEM_PROMPT
        if context:
            system_prompt = f"{_QA_SYSTEM_PROMPT}\n\n{context}"

        answer = await svc.translate(
            text=question,
            system_prompt=system_prompt,
        )
        return answer

    def _update_history(
        self, session_id: str, question: str, answer: str
    ) -> None:
        """更新对话历史

        Args:
            session_id: 会话 ID
            question: 用户问题
            answer: 助手回答
        """
        if session_id not in self._sessions:
            self._sessions[session_id] = ConversationHistory(
                session_id=session_id,
            )

        history = self._sessions[session_id]
        history.add("user", question)
        history.add("assistant", answer)
