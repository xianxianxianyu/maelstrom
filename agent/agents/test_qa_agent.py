"""Tests for QAAgent (RAG-enhanced)

Unit tests covering:
- ConversationHistory add/truncation
- QAAgent registration
- QAAgent with mocked DocSearchTool and translation_service
- Multi-turn conversation
- doc_id switching
- Low-relevance threshold behavior
- Citation generation
- Empty/invalid inputs
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from agent.agents.qa_agent import (
    ConversationHistory,
    QAAgent,
    DEFAULT_RELEVANCE_THRESHOLD,
    _LOW_RELEVANCE_MESSAGE,
)
from agent.registry import agent_registry
from agent.tools.base import ToolResult
from agent.tools.doc_search_tool import DocSearchTool, VectorIndex


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_doc_search_tool():
    """Create a mock DocSearchTool that returns configurable results."""
    tool = AsyncMock(spec=DocSearchTool)
    tool.name = "doc_search"
    tool.description = "mock doc search"
    # Default: return empty chunks
    tool.execute = AsyncMock(
        return_value=ToolResult(success=True, data={"chunks": []})
    )
    return tool


@pytest.fixture
def mock_translation_service():
    """Create a mock TranslationService."""
    svc = AsyncMock()
    svc.translate = AsyncMock(return_value="这是一个测试回答。")
    return svc


@pytest.fixture
def agent(mock_doc_search_tool, mock_translation_service):
    """Create a QAAgent with injected dependencies."""
    return QAAgent(
        doc_search_tool=mock_doc_search_tool,
        translation_service=mock_translation_service,
    )


def _make_chunks(texts_and_sources, base_score=0.8):
    """Helper to create chunk dicts for search results."""
    return [
        {"text": t, "source": s, "score": base_score - i * 0.05}
        for i, (t, s) in enumerate(texts_and_sources)
    ]


# ---------------------------------------------------------------------------
# Tests: ConversationHistory
# ---------------------------------------------------------------------------


class TestConversationHistory:
    """Test ConversationHistory dataclass."""

    def test_add_message(self):
        """Adding a message should append to messages list."""
        h = ConversationHistory(session_id="s1")
        h.add("user", "Hello")
        assert len(h.messages) == 1
        assert h.messages[0] == {"role": "user", "content": "Hello"}

    def test_add_multiple_messages(self):
        """Multiple messages should be appended in order."""
        h = ConversationHistory(session_id="s1")
        h.add("user", "Q1")
        h.add("assistant", "A1")
        h.add("user", "Q2")
        assert len(h.messages) == 3
        assert h.messages[0]["role"] == "user"
        assert h.messages[1]["role"] == "assistant"
        assert h.messages[2]["role"] == "user"

    def test_truncation_at_max_turns(self):
        """Messages should be truncated to max_turns * 2."""
        h = ConversationHistory(session_id="s1", max_turns=2)
        # Add 3 full turns (6 messages), should keep only last 4
        for i in range(3):
            h.add("user", f"Q{i}")
            h.add("assistant", f"A{i}")
        assert len(h.messages) == 4  # max_turns=2 → 4 messages
        assert h.messages[0] == {"role": "user", "content": "Q1"}
        assert h.messages[-1] == {"role": "assistant", "content": "A2"}

    def test_truncation_default_max_turns(self):
        """Default max_turns=20 means max 40 messages."""
        h = ConversationHistory(session_id="s1")
        assert h.max_turns == 20
        # Add 21 turns (42 messages)
        for i in range(21):
            h.add("user", f"Q{i}")
            h.add("assistant", f"A{i}")
        assert len(h.messages) == 40  # 20 * 2

    def test_get_context_messages_returns_copy(self):
        """get_context_messages should return a copy, not the original."""
        h = ConversationHistory(session_id="s1")
        h.add("user", "Q1")
        msgs = h.get_context_messages()
        msgs.append({"role": "user", "content": "extra"})
        assert len(h.messages) == 1  # Original unchanged

    def test_empty_history(self):
        """New history should have empty messages."""
        h = ConversationHistory(session_id="s1")
        assert h.messages == []
        assert h.get_context_messages() == []

    def test_doc_id_attribute(self):
        """doc_id should be settable."""
        h = ConversationHistory(session_id="s1", doc_id="doc-123")
        assert h.doc_id == "doc-123"
        h.doc_id = "doc-456"
        assert h.doc_id == "doc-456"


# ---------------------------------------------------------------------------
# Tests: Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    """Verify QAAgent is registered in agent_registry."""

    def test_registered_in_registry(self):
        """QAAgent should be registered under its class name."""
        assert agent_registry.get("QAAgent") is QAAgent

    def test_name_property(self, agent):
        """name property should return 'qa'."""
        assert agent.name == "qa"

    def test_description_property(self, agent):
        """description property should be non-empty."""
        assert agent.description
        assert isinstance(agent.description, str)


# ---------------------------------------------------------------------------
# Tests: Basic QA flow
# ---------------------------------------------------------------------------


class TestBasicQAFlow:
    """Test the basic question-answering flow."""

    @pytest.mark.asyncio
    async def test_basic_question_answer(
        self, agent, mock_doc_search_tool, mock_translation_service
    ):
        """Basic question should return answer and citations."""
        chunks = _make_chunks([
            ("Transformer 是一种注意力模型。", "paper.pdf - 段落 1"),
        ])
        mock_doc_search_tool.execute.return_value = ToolResult(
            success=True, data={"chunks": chunks}
        )
        mock_translation_service.translate.return_value = "Transformer 是基于注意力机制的模型。"

        result = await agent.run({"question": "什么是 Transformer？"})

        assert "answer" in result
        assert "citations" in result
        assert result["answer"] == "Transformer 是基于注意力机制的模型。"
        assert len(result["citations"]) == 1
        assert result["citations"][0]["source"] == "paper.pdf - 段落 1"

    @pytest.mark.asyncio
    async def test_no_chunks_returns_empty_citations(
        self, agent, mock_doc_search_tool, mock_translation_service
    ):
        """When no chunks are found, citations should be empty."""
        mock_doc_search_tool.execute.return_value = ToolResult(
            success=True, data={"chunks": []}
        )
        mock_translation_service.translate.return_value = "我无法找到相关信息。"

        result = await agent.run({"question": "什么是量子计算？"})

        assert result["citations"] == []
        # LLM should still be called (no chunks doesn't mean low relevance)
        mock_translation_service.translate.assert_called_once()

    @pytest.mark.asyncio
    async def test_doc_search_failure_returns_empty_citations(
        self, agent, mock_doc_search_tool, mock_translation_service
    ):
        """When DocSearch fails, should still return answer with empty citations."""
        mock_doc_search_tool.execute.return_value = ToolResult(
            success=False, error="Index not found"
        )
        mock_translation_service.translate.return_value = "抱歉，检索失败。"

        result = await agent.run({"question": "什么是 BERT？"})

        assert result["citations"] == []
        assert result["answer"] == "抱歉，检索失败。"

    @pytest.mark.asyncio
    async def test_multiple_citations(
        self, agent, mock_doc_search_tool, mock_translation_service
    ):
        """Multiple relevant chunks should produce multiple citations."""
        chunks = _make_chunks([
            ("BERT 是预训练模型。", "paper1.pdf - 段落 2"),
            ("BERT 使用 Transformer 编码器。", "paper1.pdf - 段落 5"),
            ("GPT 使用 Transformer 解码器。", "paper2.pdf - 段落 1"),
        ])
        mock_doc_search_tool.execute.return_value = ToolResult(
            success=True, data={"chunks": chunks}
        )

        result = await agent.run({"question": "BERT 和 GPT 有什么区别？"})

        assert len(result["citations"]) == 3
        sources = [c["source"] for c in result["citations"]]
        assert "paper1.pdf - 段落 2" in sources
        assert "paper2.pdf - 段落 1" in sources


# ---------------------------------------------------------------------------
# Tests: Multi-turn conversation
# ---------------------------------------------------------------------------


class TestMultiTurnConversation:
    """Test multi-turn conversation support."""

    @pytest.mark.asyncio
    async def test_conversation_history_maintained(
        self, agent, mock_doc_search_tool, mock_translation_service
    ):
        """Conversation history should be maintained across turns."""
        chunks = _make_chunks([("文档内容。", "doc.pdf")])
        mock_doc_search_tool.execute.return_value = ToolResult(
            success=True, data={"chunks": chunks}
        )
        mock_translation_service.translate.return_value = "回答1"

        # Turn 1
        await agent.run({
            "question": "问题1",
            "session_id": "session-1",
        })

        # Verify history was updated
        history = agent._sessions["session-1"]
        assert len(history.messages) == 2
        assert history.messages[0] == {"role": "user", "content": "问题1"}
        assert history.messages[1] == {"role": "assistant", "content": "回答1"}

        # Turn 2
        mock_translation_service.translate.return_value = "回答2"
        await agent.run({
            "question": "问题2",
            "session_id": "session-1",
        })

        assert len(history.messages) == 4

    @pytest.mark.asyncio
    async def test_separate_sessions(
        self, agent, mock_doc_search_tool, mock_translation_service
    ):
        """Different session_ids should have separate histories."""
        chunks = _make_chunks([("内容。", "doc.pdf")])
        mock_doc_search_tool.execute.return_value = ToolResult(
            success=True, data={"chunks": chunks}
        )
        mock_translation_service.translate.return_value = "回答"

        await agent.run({"question": "Q1", "session_id": "s1"})
        await agent.run({"question": "Q2", "session_id": "s2"})

        assert len(agent._sessions["s1"].messages) == 2
        assert len(agent._sessions["s2"].messages) == 2

    @pytest.mark.asyncio
    async def test_default_session_id(
        self, agent, mock_doc_search_tool, mock_translation_service
    ):
        """Missing session_id should default to 'default'."""
        chunks = _make_chunks([("内容。", "doc.pdf")])
        mock_doc_search_tool.execute.return_value = ToolResult(
            success=True, data={"chunks": chunks}
        )
        mock_translation_service.translate.return_value = "回答"

        await agent.run({"question": "Q1"})

        assert "default" in agent._sessions
        assert len(agent._sessions["default"].messages) == 2

    @pytest.mark.asyncio
    async def test_history_included_in_context(
        self, agent, mock_doc_search_tool, mock_translation_service
    ):
        """LLM prompt should include conversation history."""
        chunks = _make_chunks([("内容。", "doc.pdf")])
        mock_doc_search_tool.execute.return_value = ToolResult(
            success=True, data={"chunks": chunks}
        )
        mock_translation_service.translate.return_value = "回答1"

        # Turn 1
        await agent.run({"question": "问题1", "session_id": "s1"})

        # Turn 2
        mock_translation_service.translate.return_value = "回答2"
        await agent.run({"question": "问题2", "session_id": "s1"})

        # Check that the second call included history in the system prompt
        call_args = mock_translation_service.translate.call_args_list[-1]
        system_prompt = call_args.kwargs.get("system_prompt", "")
        assert "问题1" in system_prompt
        assert "回答1" in system_prompt


# ---------------------------------------------------------------------------
# Tests: doc_id switching
# ---------------------------------------------------------------------------


class TestDocIdSwitching:
    """Test doc_id switching behavior (Req 4.5)."""

    @pytest.mark.asyncio
    async def test_doc_id_passed_to_search(
        self, agent, mock_doc_search_tool, mock_translation_service
    ):
        """doc_id should be passed to DocSearchTool."""
        mock_doc_search_tool.execute.return_value = ToolResult(
            success=True, data={"chunks": []}
        )
        mock_translation_service.translate.return_value = "回答"

        await agent.run({
            "question": "Q1",
            "doc_id": "doc-123",
        })

        call_kwargs = mock_doc_search_tool.execute.call_args.kwargs
        assert call_kwargs["doc_id"] == "doc-123"

    @pytest.mark.asyncio
    async def test_doc_id_switch_preserves_history(
        self, agent, mock_doc_search_tool, mock_translation_service
    ):
        """Switching doc_id should preserve conversation history."""
        chunks = _make_chunks([("内容。", "doc.pdf")])
        mock_doc_search_tool.execute.return_value = ToolResult(
            success=True, data={"chunks": chunks}
        )
        mock_translation_service.translate.return_value = "回答"

        # Ask with doc-1
        await agent.run({
            "question": "Q1",
            "session_id": "s1",
            "doc_id": "doc-1",
        })

        assert agent._sessions["s1"].doc_id == "doc-1"
        assert len(agent._sessions["s1"].messages) == 2

        # Switch to doc-2 — history should be preserved
        await agent.run({
            "question": "Q2",
            "session_id": "s1",
            "doc_id": "doc-2",
        })

        assert agent._sessions["s1"].doc_id == "doc-2"
        assert len(agent._sessions["s1"].messages) == 4  # History preserved

    @pytest.mark.asyncio
    async def test_no_doc_id_searches_all(
        self, agent, mock_doc_search_tool, mock_translation_service
    ):
        """Without doc_id, search should not filter by document."""
        mock_doc_search_tool.execute.return_value = ToolResult(
            success=True, data={"chunks": []}
        )
        mock_translation_service.translate.return_value = "回答"

        await agent.run({"question": "Q1"})

        call_kwargs = mock_doc_search_tool.execute.call_args.kwargs
        assert "doc_id" not in call_kwargs


# ---------------------------------------------------------------------------
# Tests: Low-relevance threshold
# ---------------------------------------------------------------------------


class TestLowRelevanceThreshold:
    """Test low-relevance threshold behavior (Req 4.6)."""

    @pytest.mark.asyncio
    async def test_all_chunks_below_threshold(
        self, agent, mock_doc_search_tool, mock_translation_service
    ):
        """When all chunks are below threshold, return low-relevance message."""
        low_score_chunks = [
            {"text": "不相关内容", "source": "doc.pdf", "score": 0.1},
            {"text": "也不相关", "source": "doc.pdf", "score": 0.2},
        ]
        mock_doc_search_tool.execute.return_value = ToolResult(
            success=True, data={"chunks": low_score_chunks}
        )

        result = await agent.run({"question": "完全无关的问题"})

        assert result["answer"] == _LOW_RELEVANCE_MESSAGE
        assert result["citations"] == []
        # LLM should NOT be called when all chunks are below threshold
        mock_translation_service.translate.assert_not_called()

    @pytest.mark.asyncio
    async def test_some_chunks_above_threshold(
        self, agent, mock_doc_search_tool, mock_translation_service
    ):
        """When some chunks are above threshold, use only those."""
        mixed_chunks = [
            {"text": "相关内容", "source": "doc.pdf - 段落 1", "score": 0.8},
            {"text": "不相关", "source": "doc.pdf - 段落 5", "score": 0.1},
        ]
        mock_doc_search_tool.execute.return_value = ToolResult(
            success=True, data={"chunks": mixed_chunks}
        )
        mock_translation_service.translate.return_value = "基于相关内容的回答"

        result = await agent.run({"question": "相关问题"})

        assert result["answer"] == "基于相关内容的回答"
        # Only the above-threshold chunk should be in citations
        assert len(result["citations"]) == 1
        assert result["citations"][0]["source"] == "doc.pdf - 段落 1"

    @pytest.mark.asyncio
    async def test_custom_relevance_threshold(
        self, mock_doc_search_tool, mock_translation_service
    ):
        """Custom relevance threshold should be respected."""
        agent = QAAgent(
            doc_search_tool=mock_doc_search_tool,
            translation_service=mock_translation_service,
            relevance_threshold=0.5,
        )
        chunks = [
            {"text": "内容", "source": "doc.pdf", "score": 0.4},
        ]
        mock_doc_search_tool.execute.return_value = ToolResult(
            success=True, data={"chunks": chunks}
        )

        result = await agent.run({"question": "问题"})

        assert result["answer"] == _LOW_RELEVANCE_MESSAGE
        assert result["citations"] == []

    @pytest.mark.asyncio
    async def test_low_relevance_still_updates_history(
        self, agent, mock_doc_search_tool
    ):
        """Low-relevance response should still be added to history."""
        low_chunks = [
            {"text": "不相关", "source": "doc.pdf", "score": 0.1},
        ]
        mock_doc_search_tool.execute.return_value = ToolResult(
            success=True, data={"chunks": low_chunks}
        )

        await agent.run({
            "question": "无关问题",
            "session_id": "s1",
        })

        history = agent._sessions["s1"]
        assert len(history.messages) == 2
        assert history.messages[0]["content"] == "无关问题"
        assert history.messages[1]["content"] == _LOW_RELEVANCE_MESSAGE


# ---------------------------------------------------------------------------
# Tests: Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Test error handling for invalid inputs."""

    @pytest.mark.asyncio
    async def test_non_dict_input(self, agent):
        """Non-dict input should raise ValueError."""
        with pytest.raises(ValueError, match="must be a dict"):
            await agent.run("not a dict")

    @pytest.mark.asyncio
    async def test_missing_question(self, agent):
        """Missing question field should raise ValueError."""
        with pytest.raises(ValueError, match="question"):
            await agent.run({})

    @pytest.mark.asyncio
    async def test_empty_question(self, agent):
        """Empty question should raise ValueError."""
        with pytest.raises(ValueError, match="question"):
            await agent.run({"question": ""})

    @pytest.mark.asyncio
    async def test_whitespace_question(self, agent):
        """Whitespace-only question should raise ValueError."""
        with pytest.raises(ValueError, match="question"):
            await agent.run({"question": "   "})

    @pytest.mark.asyncio
    async def test_non_string_question(self, agent):
        """Non-string question should raise ValueError."""
        with pytest.raises(ValueError, match="question"):
            await agent.run({"question": 123})

    @pytest.mark.asyncio
    async def test_callable_interface(
        self, agent, mock_doc_search_tool, mock_translation_service
    ):
        """Agent should work via __call__ (setup -> run -> teardown)."""
        mock_doc_search_tool.execute.return_value = ToolResult(
            success=True, data={"chunks": []}
        )
        mock_translation_service.translate.return_value = "回答"

        result = await agent({"question": "测试问题"})
        assert "answer" in result
        assert "citations" in result


# ---------------------------------------------------------------------------
# Tests: Integration with real DocSearchTool
# ---------------------------------------------------------------------------


class TestIntegrationWithDocSearch:
    """Integration tests using real DocSearchTool + VectorIndex."""

    @pytest_asyncio.fixture
    async def real_agent(self, mock_translation_service):
        """Create QAAgent with real DocSearchTool.

        Uses relevance_threshold=0.0 because hash-based embeddings (MVP)
        produce very low cosine similarity scores.
        """
        index = VectorIndex()
        tool = DocSearchTool(vector_index=index)
        # Index a test document
        await index.index_document(
            "doc-1",
            "Transformer 是一种基于注意力机制的深度学习模型。\n\n"
            "BERT 是基于 Transformer 编码器的预训练语言模型。\n\n"
            "GPT 使用 Transformer 解码器进行文本生成。",
            "test_paper.pdf",
        )
        return QAAgent(
            doc_search_tool=tool,
            translation_service=mock_translation_service,
            relevance_threshold=0.0,  # Hash embeddings produce low scores
        )

    @pytest.mark.asyncio
    async def test_real_search_returns_citations(
        self, real_agent, mock_translation_service
    ):
        """Real search should return relevant citations."""
        mock_translation_service.translate.return_value = "Transformer 是注意力模型。"

        result = await real_agent.run({
            "question": "Transformer",
            "doc_id": "doc-1",
        })

        assert len(result["citations"]) > 0
        assert all(
            c["source"] == "test_paper.pdf" for c in result["citations"]
        )

    @pytest.mark.asyncio
    async def test_real_search_with_doc_id_isolation(
        self, mock_translation_service
    ):
        """Search with doc_id should only return chunks from that doc."""
        index = VectorIndex()
        tool = DocSearchTool(vector_index=index)

        await index.index_document("doc-A", "Alpha 内容", "alpha.pdf")
        await index.index_document("doc-B", "Beta 内容", "beta.pdf")

        agent = QAAgent(
            doc_search_tool=tool,
            translation_service=mock_translation_service,
            relevance_threshold=0.0,  # Hash embeddings produce low scores
        )
        mock_translation_service.translate.return_value = "回答"

        result = await agent.run({
            "question": "内容",
            "doc_id": "doc-A",
        })

        # All citations should be from doc-A
        for c in result["citations"]:
            assert c["source"] == "alpha.pdf"
