"""Tests for TranslationAgent

Unit tests covering:
- Registration in agent_registry
- _generate_prompt with glossary injection
- _execute_with_retry with failures and retries
- Cancellation token check
- Progress events published via EventBus
- Full run() flow (prompt generation → translation execution)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from agent.agents.translation_agent import TranslationAgent
from agent.context import AgentContext
from agent.event_bus import EventBus
from agent.registry import agent_registry
from backend.app.services.pipelines.base import (
    CancellationToken,
    PipelineResult,
)
from backend.app.services.prompt_generator import PromptProfile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def event_bus():
    """Create a fresh EventBus."""
    return EventBus()


@pytest_asyncio.fixture
async def mock_ocr_tool():
    """Create a mock OCRTool."""
    tool = AsyncMock()
    tool.name = "ocr"
    return tool


@pytest_asyncio.fixture
async def mock_translate_tool():
    """Create a mock TranslateTool."""
    tool = AsyncMock()
    tool.name = "translate"
    return tool


@pytest_asyncio.fixture
async def agent(mock_ocr_tool, mock_translate_tool):
    """Create a TranslationAgent with injected mock tools."""
    return TranslationAgent(
        ocr_tool=mock_ocr_tool,
        translate_tool=mock_translate_tool,
    )


@pytest_asyncio.fixture
async def ctx(event_bus):
    """Create a minimal AgentContext for testing.

    pipeline_type is pre-set to 'llm' to simulate OCRAgent having run first.
    """
    return AgentContext(
        task_id="test-task-001",
        filename="test.pdf",
        file_content=b"%PDF-1.4 fake content",
        event_bus=event_bus,
        glossary={"Transformer": "Transformer模型", "attention": "注意力"},
        pipeline_type="llm",
    )


# ---------------------------------------------------------------------------
# Tests: Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    """Verify TranslationAgent is registered in agent_registry."""

    def test_registered_in_registry(self):
        """TranslationAgent should be registered under its class name."""
        assert agent_registry.get("TranslationAgent") is TranslationAgent

    def test_name_property(self, agent: TranslationAgent):
        """name property should return 'translation'."""
        assert agent.name == "translation"

    def test_description_property(self, agent: TranslationAgent):
        """description property should be non-empty."""
        assert agent.description
        assert isinstance(agent.description, str)


# ---------------------------------------------------------------------------
# Tests: _generate_prompt
# ---------------------------------------------------------------------------


class TestGeneratePrompt:
    """Test prompt generation with glossary injection."""

    @pytest.mark.asyncio
    async def test_glossary_injected_into_profile(
        self, agent: TranslationAgent, ctx: AgentContext
    ):
        """Glossary terms from ctx should be injected into the profile."""
        profile = await agent._generate_prompt(ctx)

        assert isinstance(profile, PromptProfile)
        # Glossary terms should be in terminology
        assert "Transformer" in profile.terminology
        assert profile.terminology["Transformer"] == "Transformer模型"
        assert "attention" in profile.terminology
        assert profile.terminology["attention"] == "注意力"

    @pytest.mark.asyncio
    async def test_prompt_contains_glossary_terms(
        self, agent: TranslationAgent, ctx: AgentContext
    ):
        """Generated translation_prompt should contain glossary terms."""
        profile = await agent._generate_prompt(ctx)

        assert "Transformer" in profile.translation_prompt
        assert "attention" in profile.translation_prompt

    @pytest.mark.asyncio
    async def test_empty_glossary(
        self, agent: TranslationAgent, event_bus: EventBus
    ):
        """Empty glossary should still produce a valid profile."""
        ctx = AgentContext(
            task_id="test-002",
            filename="test.pdf",
            file_content=b"%PDF-1.4",
            event_bus=event_bus,
            glossary={},
            pipeline_type="llm",
        )
        profile = await agent._generate_prompt(ctx)
        assert isinstance(profile, PromptProfile)
        assert profile.translation_prompt  # Should have default prompt


# ---------------------------------------------------------------------------
# Tests: _execute_with_retry
# ---------------------------------------------------------------------------


class TestExecuteWithRetry:
    """Test retry logic for translation execution."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(
        self, agent: TranslationAgent, ctx: AgentContext
    ):
        """Should succeed on first attempt without retries."""
        expected_result = PipelineResult(translated_md="翻译结果")

        with patch.object(
            agent, "_run_pipeline", new_callable=AsyncMock, return_value=expected_result
        ):
            result = await agent._execute_with_retry("llm", ctx, max_retries=3)

        assert result.translated_md == "翻译结果"

    @pytest.mark.asyncio
    async def test_success_after_retries(
        self, agent: TranslationAgent, ctx: AgentContext
    ):
        """Should succeed after initial failures."""
        expected_result = PipelineResult(translated_md="翻译结果")

        call_count = 0

        async def mock_run_pipeline(pipeline_type, context):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("Temporary failure")
            return expected_result

        with patch.object(agent, "_run_pipeline", side_effect=mock_run_pipeline):
            result = await agent._execute_with_retry("llm", ctx, max_retries=3)

        assert result.translated_md == "翻译结果"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(
        self, agent: TranslationAgent, ctx: AgentContext
    ):
        """Should raise RuntimeError when all retries fail."""
        with patch.object(
            agent,
            "_run_pipeline",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Persistent failure"),
        ):
            with pytest.raises(RuntimeError, match="Translation failed after 3 attempts"):
                await agent._execute_with_retry("llm", ctx, max_retries=3)

    @pytest.mark.asyncio
    async def test_cancellation_stops_retry(
        self, agent: TranslationAgent, ctx: AgentContext
    ):
        """Cancellation should stop retries immediately."""
        call_count = 0

        async def mock_run_pipeline(pipeline_type, context):
            nonlocal call_count
            call_count += 1
            # Cancel after first attempt
            ctx.cancellation_token.cancel()
            raise RuntimeError("Failure")

        with patch.object(agent, "_run_pipeline", side_effect=mock_run_pipeline):
            with pytest.raises(asyncio.CancelledError):
                await agent._execute_with_retry("llm", ctx, max_retries=3)

        assert call_count == 1  # Should not retry after cancellation

    @pytest.mark.asyncio
    async def test_retry_publishes_progress_events(
        self, agent: TranslationAgent, ctx: AgentContext, event_bus: EventBus
    ):
        """Each retry should publish a progress event."""
        queue = event_bus.subscribe(ctx.task_id)
        expected_result = PipelineResult(translated_md="结果")

        call_count = 0

        async def mock_run_pipeline(pipeline_type, context):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("Temporary failure")
            return expected_result

        with patch.object(agent, "_run_pipeline", side_effect=mock_run_pipeline):
            await agent._execute_with_retry("llm", ctx, max_retries=3)

        # Collect all events
        events = []
        while not queue.empty():
            events.append(await queue.get())

        # Should have retry event + success event
        assert len(events) >= 2
        # First event should be a retry
        assert events[0]["detail"]["status"] == "retry"
        # Last event should be success
        assert events[-1]["detail"]["status"] == "success"


# ---------------------------------------------------------------------------
# Tests: Full run() flow
# ---------------------------------------------------------------------------


class TestRunFlow:
    """Test the complete run() method."""

    @pytest.mark.asyncio
    async def test_full_run_publishes_stages(
        self, agent: TranslationAgent, ctx: AgentContext, event_bus: EventBus
    ):
        """run() should publish events for prompt_generation, translating, complete."""
        queue = event_bus.subscribe(ctx.task_id)
        expected_result = PipelineResult(translated_md="完整翻译结果")

        with patch.object(
            agent,
            "_generate_prompt",
            new_callable=AsyncMock,
            return_value=PromptProfile(
                domain="NLP",
                terminology={"Transformer": "Transformer模型"},
                translation_prompt="test prompt",
            ),
        ), patch.object(
            agent,
            "_execute_with_retry",
            new_callable=AsyncMock,
            return_value=expected_result,
        ):
            result = await agent.run(ctx)

        assert result.translated_md == "完整翻译结果"
        assert result.prompt_profile is not None

        # Collect all events
        events = []
        while not queue.empty():
            events.append(await queue.get())

        stages = [e["stage"] for e in events]
        assert "prompt_generation" in stages
        assert "translating" in stages
        assert "complete" in stages

        # All events should have agent="translation"
        for event in events:
            assert event["agent"] == "translation"

        # Progress should be monotonically non-decreasing
        progress_values = [e["progress"] for e in events]
        for i in range(1, len(progress_values)):
            assert progress_values[i] >= progress_values[i - 1]

    @pytest.mark.asyncio
    async def test_run_sets_translated_md(
        self, agent: TranslationAgent, ctx: AgentContext
    ):
        """run() should set ctx.translated_md."""
        expected_result = PipelineResult(translated_md="翻译后的文本")

        with patch.object(
            agent,
            "_generate_prompt",
            new_callable=AsyncMock,
            return_value=PromptProfile(translation_prompt="prompt"),
        ), patch.object(
            agent,
            "_execute_with_retry",
            new_callable=AsyncMock,
            return_value=expected_result,
        ):
            result = await agent.run(ctx)

        assert result.translated_md == "翻译后的文本"
        assert ctx.translated_md == "翻译后的文本"

    @pytest.mark.asyncio
    async def test_run_sets_prompt_profile(
        self, agent: TranslationAgent, ctx: AgentContext
    ):
        """run() should set ctx.prompt_profile."""
        profile = PromptProfile(
            domain="CV", translation_prompt="test prompt"
        )
        expected_result = PipelineResult(translated_md="result")

        with patch.object(
            agent,
            "_generate_prompt",
            new_callable=AsyncMock,
            return_value=profile,
        ), patch.object(
            agent,
            "_execute_with_retry",
            new_callable=AsyncMock,
            return_value=expected_result,
        ):
            result = await agent.run(ctx)

        assert ctx.prompt_profile is profile
        assert ctx.prompt_profile.domain == "CV"

    @pytest.mark.asyncio
    async def test_auto_fix_rerun_skips_prompt_generation(
        self, agent: TranslationAgent, ctx: AgentContext
    ):
        """When prompt_profile exists and translated_md is set, should skip prompt generation."""
        ctx.prompt_profile = PromptProfile(
            domain="NLP", translation_prompt="existing prompt"
        )
        ctx.translated_md = "旧翻译"

        expected_result = PipelineResult(translated_md="修正翻译")

        with patch.object(
            agent,
            "_generate_prompt",
            new_callable=AsyncMock,
        ) as mock_gen, patch.object(
            agent,
            "_execute_with_retry",
            new_callable=AsyncMock,
            return_value=expected_result,
        ):
            result = await agent.run(ctx)

        # _generate_prompt should NOT have been called
        mock_gen.assert_not_called()
        assert result.translated_md == "修正翻译"

    @pytest.mark.asyncio
    async def test_run_uses_pipeline_type_from_context(
        self, agent: TranslationAgent, event_bus: EventBus
    ):
        """run() should use ctx.pipeline_type set by OCRAgent."""
        ctx = AgentContext(
            task_id="test-003",
            filename="test.pdf",
            file_content=b"%PDF-1.4",
            event_bus=event_bus,
            pipeline_type="ocr",
        )
        expected_result = PipelineResult(translated_md="OCR翻译结果")

        with patch.object(
            agent,
            "_generate_prompt",
            new_callable=AsyncMock,
            return_value=PromptProfile(translation_prompt="prompt"),
        ), patch.object(
            agent,
            "_execute_with_retry",
            new_callable=AsyncMock,
            return_value=expected_result,
        ) as mock_retry:
            await agent.run(ctx)

        # Should have been called with "ocr" pipeline type
        mock_retry.assert_called_once()
        assert mock_retry.call_args[0][0] == "ocr"

    @pytest.mark.asyncio
    async def test_run_defaults_to_llm_pipeline(
        self, agent: TranslationAgent, event_bus: EventBus
    ):
        """run() should default to 'llm' when pipeline_type is empty."""
        ctx = AgentContext(
            task_id="test-004",
            filename="test.pdf",
            file_content=b"%PDF-1.4",
            event_bus=event_bus,
            pipeline_type="",
        )
        expected_result = PipelineResult(translated_md="LLM翻译结果")

        with patch.object(
            agent,
            "_generate_prompt",
            new_callable=AsyncMock,
            return_value=PromptProfile(translation_prompt="prompt"),
        ), patch.object(
            agent,
            "_execute_with_retry",
            new_callable=AsyncMock,
            return_value=expected_result,
        ) as mock_retry:
            await agent.run(ctx)

        mock_retry.assert_called_once()
        assert mock_retry.call_args[0][0] == "llm"
