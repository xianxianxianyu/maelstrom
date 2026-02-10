"""Tests for OrchestratorAgent

Unit tests covering:
- Registration in agent_registry
- Workflow order (terminology → translation → review)
- SSE events published at each phase
- Auto-fix when quality score < 70
- No auto-fix when quality score >= 70
- Cancellation handling
- Agent failure handling
- Save results to TranslationStore
- Dependency injection
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from agent.agents.orchestrator_agent import (
    OrchestratorAgent,
    QUALITY_THRESHOLD,
    MAX_AUTO_FIX_RETRIES,
)
from agent.context import AgentContext
from agent.event_bus import EventBus
from agent.models import QualityReport
from agent.registry import agent_registry
from backend.app.services.pipelines.base import CancellationToken


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_quality_report(score: int, suggestions: list[str] | None = None) -> QualityReport:
    """Create a QualityReport with the given score."""
    return QualityReport(
        score=score,
        suggestions=suggestions or [],
        timestamp="2024-01-01T00:00:00+00:00",
    )


def _make_mock_terminology_agent(glossary_result: dict | None = None):
    """Create a mock TerminologyAgent."""
    agent = AsyncMock()
    agent.name = "terminology"
    result = glossary_result or {"glossary": [], "conflicts": []}
    agent.return_value = result
    return agent


def _make_mock_ocr_agent():
    """Create a mock OCRAgent that sets pipeline_type on ctx."""
    agent = AsyncMock()
    agent.name = "ocr"

    async def ocr_side_effect(ctx, **kwargs):
        ctx.pipeline_type = "llm"
        return ctx

    agent.side_effect = ocr_side_effect
    return agent


def _make_mock_translation_agent(translated_md: str = "翻译结果"):
    """Create a mock TranslationAgent that sets translated_md on ctx."""
    agent = AsyncMock()
    agent.name = "translation"

    async def translate_side_effect(ctx, **kwargs):
        ctx.translated_md = translated_md
        return ctx

    agent.side_effect = translate_side_effect
    return agent


def _make_mock_review_agent(score: int = 85, suggestions: list[str] | None = None):
    """Create a mock ReviewAgent that sets quality_report on ctx."""
    agent = AsyncMock()
    agent.name = "review"

    async def review_side_effect(ctx, **kwargs):
        ctx.quality_report = _make_quality_report(score, suggestions)
        return ctx

    agent.side_effect = review_side_effect
    return agent


def _make_mock_store():
    """Create a mock TranslationStore."""
    store = AsyncMock()
    store.save = AsyncMock(return_value={"id": "abc123", "filename": "test.pdf"})
    return store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def event_bus():
    """Create a fresh EventBus."""
    return EventBus()


@pytest_asyncio.fixture
async def ctx(event_bus):
    """Create a minimal AgentContext for testing."""
    return AgentContext(
        task_id="test-orch-001",
        filename="test.pdf",
        file_content=b"%PDF-1.4 fake content",
        event_bus=event_bus,
    )


@pytest.fixture
def agent():
    """Create an OrchestratorAgent with all mocked sub-agents."""
    return OrchestratorAgent(
        terminology_agent=_make_mock_terminology_agent({
            "glossary": [
                {"english": "Transformer", "chinese": "变换器"},
                {"english": "attention", "chinese": "注意力"},
            ],
            "conflicts": [],
        }),
        ocr_agent=_make_mock_ocr_agent(),
        translation_agent=_make_mock_translation_agent("翻译后的文本"),
        review_agent=_make_mock_review_agent(score=85),
        translation_store=_make_mock_store(),
    )


# ---------------------------------------------------------------------------
# Tests: Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    """Verify OrchestratorAgent is registered in agent_registry."""

    def test_registered_in_registry(self):
        """OrchestratorAgent should be registered under its class name."""
        assert agent_registry.get("OrchestratorAgent") is OrchestratorAgent

    def test_name_property(self, agent: OrchestratorAgent):
        """name property should return 'orchestrator'."""
        assert agent.name == "orchestrator"

    def test_description_property(self, agent: OrchestratorAgent):
        """description property should be non-empty."""
        assert agent.description
        assert isinstance(agent.description, str)


# ---------------------------------------------------------------------------
# Tests: Workflow Order
# ---------------------------------------------------------------------------


class TestWorkflowOrder:
    """Test that agents are called in the correct order."""

    @pytest.mark.asyncio
    async def test_agents_called_in_order(self, ctx: AgentContext):
        """Agents should be called: terminology → ocr → translation → review."""
        call_order = []

        async def term_side_effect(input_data, **kwargs):
            call_order.append("terminology")
            return {"glossary": [], "conflicts": []}

        async def ocr_side_effect(input_data, **kwargs):
            call_order.append("ocr")
            input_data.pipeline_type = "llm"
            return input_data

        async def trans_side_effect(input_data, **kwargs):
            call_order.append("translation")
            input_data.translated_md = "翻译结果"
            return input_data

        async def review_side_effect(input_data, **kwargs):
            call_order.append("review")
            input_data.quality_report = _make_quality_report(90)
            return input_data

        term_agent = AsyncMock(side_effect=term_side_effect)
        ocr_agent = AsyncMock(side_effect=ocr_side_effect)
        trans_agent = AsyncMock(side_effect=trans_side_effect)
        review_agent = AsyncMock(side_effect=review_side_effect)

        orch = OrchestratorAgent(
            terminology_agent=term_agent,
            ocr_agent=ocr_agent,
            translation_agent=trans_agent,
            review_agent=review_agent,
            translation_store=_make_mock_store(),
        )

        await orch.run(ctx)

        assert call_order == ["terminology", "ocr", "translation", "review"]

    @pytest.mark.asyncio
    async def test_all_four_agents_called(self, agent, ctx):
        """All four sub-agents should be called exactly once."""
        await agent.run(ctx)

        agent._terminology_agent.assert_called_once()
        agent._ocr_agent.assert_called_once()
        agent._translation_agent.assert_called_once()
        agent._review_agent.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: SSE Events
# ---------------------------------------------------------------------------


class TestSSEEvents:
    """Test SSE events published at each phase."""

    @pytest.mark.asyncio
    async def test_events_published_for_all_phases(
        self, agent, ctx, event_bus
    ):
        """Events should be published for terminology, translation, review, saving, complete."""
        queue = event_bus.subscribe(ctx.task_id)

        await agent.run(ctx)

        events = []
        while not queue.empty():
            events.append(await queue.get())

        stages = [e["stage"] for e in events]
        assert "terminology" in stages
        assert "ocr" in stages
        assert "translation" in stages
        assert "review" in stages
        assert "saving" in stages
        assert "complete" in stages

    @pytest.mark.asyncio
    async def test_all_events_have_required_fields(
        self, agent, ctx, event_bus
    ):
        """Every event should have agent, stage, and progress fields."""
        queue = event_bus.subscribe(ctx.task_id)

        await agent.run(ctx)

        events = []
        while not queue.empty():
            events.append(await queue.get())

        assert len(events) > 0
        for event in events:
            assert "agent" in event, f"Missing 'agent' in event: {event}"
            assert "stage" in event, f"Missing 'stage' in event: {event}"
            assert "progress" in event, f"Missing 'progress' in event: {event}"
            assert event["agent"] == "orchestrator"

    @pytest.mark.asyncio
    async def test_progress_monotonically_increasing(
        self, agent, ctx, event_bus
    ):
        """Progress values should be monotonically non-decreasing."""
        queue = event_bus.subscribe(ctx.task_id)

        await agent.run(ctx)

        events = []
        while not queue.empty():
            events.append(await queue.get())

        progress_values = [e["progress"] for e in events]
        for i in range(1, len(progress_values)):
            assert progress_values[i] >= progress_values[i - 1], (
                f"Progress decreased: {progress_values[i - 1]} → {progress_values[i]} "
                f"at events {events[i - 1]['stage']} → {events[i]['stage']}"
            )

    @pytest.mark.asyncio
    async def test_final_event_is_complete_100(
        self, agent, ctx, event_bus
    ):
        """Last event should be stage='complete' with progress=100."""
        queue = event_bus.subscribe(ctx.task_id)

        await agent.run(ctx)

        events = []
        while not queue.empty():
            events.append(await queue.get())

        last_event = events[-1]
        assert last_event["stage"] == "complete"
        assert last_event["progress"] == 100


# ---------------------------------------------------------------------------
# Tests: Auto-fix
# ---------------------------------------------------------------------------


class TestAutoFix:
    """Test auto-fix behavior when quality score is below threshold."""

    @pytest.mark.asyncio
    async def test_auto_fix_triggered_when_score_below_70(self, ctx):
        """Auto-fix should trigger when score < 70."""
        call_count = {"translation": 0, "review": 0}

        async def trans_side_effect(input_data, **kwargs):
            call_count["translation"] += 1
            input_data.translated_md = f"翻译结果v{call_count['translation']}"
            return input_data

        async def review_side_effect(input_data, **kwargs):
            call_count["review"] += 1
            # First review: low score, second review: high score
            score = 50 if call_count["review"] == 1 else 85
            input_data.quality_report = _make_quality_report(
                score, ["建议1", "建议2"]
            )
            return input_data

        orch = OrchestratorAgent(
            terminology_agent=_make_mock_terminology_agent(),
            ocr_agent=_make_mock_ocr_agent(),
            translation_agent=AsyncMock(side_effect=trans_side_effect),
            review_agent=AsyncMock(side_effect=review_side_effect),
            translation_store=_make_mock_store(),
        )

        result = await orch.run(ctx)

        # Translation called twice (initial + auto-fix)
        assert call_count["translation"] == 2
        # Review called twice (initial + auto-fix)
        assert call_count["review"] == 2
        # Final score should be from second review
        assert result.quality_report.score == 85

    @pytest.mark.asyncio
    async def test_no_auto_fix_when_score_at_70(self, ctx):
        """No auto-fix when score == 70 (threshold is strictly less than)."""
        orch = OrchestratorAgent(
            terminology_agent=_make_mock_terminology_agent(),
            ocr_agent=_make_mock_ocr_agent(),
            translation_agent=_make_mock_translation_agent(),
            review_agent=_make_mock_review_agent(score=70),
            translation_store=_make_mock_store(),
        )

        result = await orch.run(ctx)

        assert result.quality_report.score == 70
        # Translation and review each called only once
        orch._translation_agent.assert_called_once()
        orch._review_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_auto_fix_when_score_above_70(self, agent, ctx):
        """No auto-fix when score > 70."""
        result = await agent.run(ctx)

        assert result.quality_report.score == 85
        agent._translation_agent.assert_called_once()
        agent._review_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_fix_max_one_retry(self, ctx):
        """Auto-fix should only retry once even if score stays low."""
        call_count = {"translation": 0, "review": 0}

        async def trans_side_effect(input_data, **kwargs):
            call_count["translation"] += 1
            input_data.translated_md = "翻译结果"
            return input_data

        async def review_side_effect(input_data, **kwargs):
            call_count["review"] += 1
            # Always return low score
            input_data.quality_report = _make_quality_report(30)
            return input_data

        orch = OrchestratorAgent(
            terminology_agent=_make_mock_terminology_agent(),
            ocr_agent=_make_mock_ocr_agent(),
            translation_agent=AsyncMock(side_effect=trans_side_effect),
            review_agent=AsyncMock(side_effect=review_side_effect),
            translation_store=_make_mock_store(),
        )

        result = await orch.run(ctx)

        # Translation: 1 initial + 1 auto-fix = 2
        assert call_count["translation"] == 2
        # Review: 1 initial + 1 auto-fix = 2
        assert call_count["review"] == 2
        # Score still low but we accept it
        assert result.quality_report.score == 30

    @pytest.mark.asyncio
    async def test_auto_fix_events_published(self, ctx, event_bus):
        """Auto-fix should publish auto_fix stage events."""
        queue = event_bus.subscribe(ctx.task_id)

        orch = OrchestratorAgent(
            terminology_agent=_make_mock_terminology_agent(),
            ocr_agent=_make_mock_ocr_agent(),
            translation_agent=_make_mock_translation_agent(),
            review_agent=_make_mock_review_agent(score=50),
            translation_store=_make_mock_store(),
        )

        await orch.run(ctx)

        events = []
        while not queue.empty():
            events.append(await queue.get())

        stages = [e["stage"] for e in events]
        assert "auto_fix" in stages


# ---------------------------------------------------------------------------
# Tests: Cancellation
# ---------------------------------------------------------------------------


class TestCancellation:
    """Test cancellation handling via CancellationToken."""

    @pytest.mark.asyncio
    async def test_cancellation_before_terminology(self, agent, ctx):
        """Cancellation before terminology phase should raise CancelledError."""
        ctx.cancellation_token.cancel()

        with pytest.raises(asyncio.CancelledError):
            await agent.run(ctx)

        # No agents should have been called
        agent._terminology_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancellation_after_terminology(self, ctx):
        """Cancellation after terminology should stop before translation."""
        call_order = []

        async def term_side_effect(input_data, **kwargs):
            call_order.append("terminology")
            ctx.cancellation_token.cancel()
            return {"glossary": [], "conflicts": []}

        orch = OrchestratorAgent(
            terminology_agent=AsyncMock(side_effect=term_side_effect),
            ocr_agent=_make_mock_ocr_agent(),
            translation_agent=_make_mock_translation_agent(),
            review_agent=_make_mock_review_agent(),
            translation_store=_make_mock_store(),
        )

        with pytest.raises(asyncio.CancelledError):
            await orch.run(ctx)

        assert call_order == ["terminology"]
        orch._translation_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancellation_during_translation(self, ctx):
        """Cancellation during translation should propagate CancelledError."""
        async def trans_side_effect(input_data, **kwargs):
            raise asyncio.CancelledError("cancelled")

        orch = OrchestratorAgent(
            terminology_agent=_make_mock_terminology_agent(),
            ocr_agent=_make_mock_ocr_agent(),
            translation_agent=AsyncMock(side_effect=trans_side_effect),
            review_agent=_make_mock_review_agent(),
            translation_store=_make_mock_store(),
        )

        with pytest.raises(asyncio.CancelledError):
            await orch.run(ctx)

        orch._review_agent.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Agent Failure Handling
# ---------------------------------------------------------------------------


class TestAgentFailureHandling:
    """Test graceful handling of agent failures."""

    @pytest.mark.asyncio
    async def test_terminology_failure_continues(self, ctx):
        """Terminology failure should not stop the workflow."""
        async def term_side_effect(input_data, **kwargs):
            raise RuntimeError("LLM unavailable")

        orch = OrchestratorAgent(
            terminology_agent=AsyncMock(side_effect=term_side_effect),
            ocr_agent=_make_mock_ocr_agent(),
            translation_agent=_make_mock_translation_agent(),
            review_agent=_make_mock_review_agent(),
            translation_store=_make_mock_store(),
        )

        result = await orch.run(ctx)

        # Workflow should complete despite terminology failure
        assert result.translated_md == "翻译结果"
        assert result.quality_report is not None

    @pytest.mark.asyncio
    async def test_translation_failure_propagates(self, ctx):
        """Translation failure should propagate (critical phase)."""
        async def trans_side_effect(input_data, **kwargs):
            raise RuntimeError("Translation failed")

        orch = OrchestratorAgent(
            terminology_agent=_make_mock_terminology_agent(),
            ocr_agent=_make_mock_ocr_agent(),
            translation_agent=AsyncMock(side_effect=trans_side_effect),
            review_agent=_make_mock_review_agent(),
            translation_store=_make_mock_store(),
        )

        with pytest.raises(RuntimeError, match="Translation failed"):
            await orch.run(ctx)

    @pytest.mark.asyncio
    async def test_review_failure_propagates(self, ctx):
        """Review failure should propagate (critical phase)."""
        async def review_side_effect(input_data, **kwargs):
            raise RuntimeError("Review failed")

        orch = OrchestratorAgent(
            terminology_agent=_make_mock_terminology_agent(),
            ocr_agent=_make_mock_ocr_agent(),
            translation_agent=_make_mock_translation_agent(),
            review_agent=AsyncMock(side_effect=review_side_effect),
            translation_store=_make_mock_store(),
        )

        with pytest.raises(RuntimeError, match="Review failed"):
            await orch.run(ctx)

    @pytest.mark.asyncio
    async def test_auto_fix_translation_failure_keeps_original(self, ctx):
        """Auto-fix translation failure should keep original translation."""
        call_count = {"translation": 0}

        async def trans_side_effect(input_data, **kwargs):
            call_count["translation"] += 1
            if call_count["translation"] == 1:
                input_data.translated_md = "原始翻译"
                return input_data
            raise RuntimeError("Auto-fix translation failed")

        orch = OrchestratorAgent(
            terminology_agent=_make_mock_terminology_agent(),
            ocr_agent=_make_mock_ocr_agent(),
            translation_agent=AsyncMock(side_effect=trans_side_effect),
            review_agent=_make_mock_review_agent(score=50),
            translation_store=_make_mock_store(),
        )

        result = await orch.run(ctx)

        # Original translation should be preserved
        assert result.translated_md == "原始翻译"

    @pytest.mark.asyncio
    async def test_save_failure_does_not_crash(self, ctx):
        """Save failure should not crash the workflow."""
        mock_store = AsyncMock()
        mock_store.save = AsyncMock(side_effect=RuntimeError("Disk full"))

        orch = OrchestratorAgent(
            terminology_agent=_make_mock_terminology_agent(),
            ocr_agent=_make_mock_ocr_agent(),
            translation_agent=_make_mock_translation_agent(),
            review_agent=_make_mock_review_agent(),
            translation_store=mock_store,
        )

        # Should not raise
        result = await orch.run(ctx)
        assert result.translated_md == "翻译结果"


# ---------------------------------------------------------------------------
# Tests: Save Results
# ---------------------------------------------------------------------------


class TestSaveResults:
    """Test saving results to TranslationStore."""

    @pytest.mark.asyncio
    async def test_save_called_with_correct_args(self, agent, ctx):
        """TranslationStore.save should be called with filename and translated_md."""
        await agent.run(ctx)

        agent._translation_store.save.assert_called_once()
        call_kwargs = agent._translation_store.save.call_args.kwargs
        assert call_kwargs["filename"] == "test.pdf"
        assert call_kwargs["translated_md"] == "翻译后的文本"

    @pytest.mark.asyncio
    async def test_save_includes_quality_report(self, agent, ctx):
        """Save should include quality_report in meta_extra."""
        await agent.run(ctx)

        call_kwargs = agent._translation_store.save.call_args.kwargs
        meta_extra = call_kwargs.get("meta_extra", {})
        assert "quality_report" in meta_extra
        assert meta_extra["quality_report"]["score"] == 85

    @pytest.mark.asyncio
    async def test_save_without_quality_report(self, ctx):
        """Save should work even without quality_report."""
        async def review_side_effect(input_data, **kwargs):
            # Don't set quality_report
            return input_data

        orch = OrchestratorAgent(
            terminology_agent=_make_mock_terminology_agent(),
            ocr_agent=_make_mock_ocr_agent(),
            translation_agent=_make_mock_translation_agent(),
            review_agent=AsyncMock(side_effect=review_side_effect),
            translation_store=_make_mock_store(),
        )

        # quality_report is None, so no auto-fix and save should still work
        result = await orch.run(ctx)
        orch._translation_store.save.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: Context Data Flow
# ---------------------------------------------------------------------------


class TestContextDataFlow:
    """Test that data flows correctly through the context."""

    @pytest.mark.asyncio
    async def test_glossary_populated_from_terminology(self, ctx):
        """ctx.glossary should be populated from terminology agent results."""
        orch = OrchestratorAgent(
            terminology_agent=_make_mock_terminology_agent({
                "glossary": [
                    {"english": "Transformer", "chinese": "变换器"},
                    {"english": "attention", "chinese": "注意力"},
                ],
                "conflicts": [],
            }),
            ocr_agent=_make_mock_ocr_agent(),
            translation_agent=_make_mock_translation_agent(),
            review_agent=_make_mock_review_agent(),
            translation_store=_make_mock_store(),
        )

        result = await orch.run(ctx)

        assert "Transformer" in result.glossary
        assert result.glossary["Transformer"] == "变换器"
        assert "attention" in result.glossary
        assert result.glossary["attention"] == "注意力"

    @pytest.mark.asyncio
    async def test_translated_md_set_by_translation_agent(self, agent, ctx):
        """ctx.translated_md should be set by translation agent."""
        result = await agent.run(ctx)
        assert result.translated_md == "翻译后的文本"

    @pytest.mark.asyncio
    async def test_quality_report_set_by_review_agent(self, agent, ctx):
        """ctx.quality_report should be set by review agent."""
        result = await agent.run(ctx)
        assert result.quality_report is not None
        assert result.quality_report.score == 85

    @pytest.mark.asyncio
    async def test_run_returns_same_context(self, agent, ctx):
        """run() should return the same context object."""
        result = await agent.run(ctx)
        assert result is ctx

    @pytest.mark.asyncio
    async def test_callable_interface(self, agent, ctx):
        """Agent should work via __call__ (setup -> run -> teardown)."""
        result = await agent(ctx)
        assert result.translated_md == "翻译后的文本"
        assert result.quality_report is not None


# ---------------------------------------------------------------------------
# Tests: Extract Text Helper
# ---------------------------------------------------------------------------


class TestExtractText:
    """Test the _extract_text_from_content helper."""

    def test_extract_text_without_fitz(self):
        """Should return empty string when fitz is not available."""
        with patch.dict("sys.modules", {"fitz": None}):
            text = OrchestratorAgent._extract_text_from_content(b"fake pdf")
        assert text == ""

    def test_extract_text_with_invalid_content(self):
        """Should return empty string for invalid content."""
        text = OrchestratorAgent._extract_text_from_content(b"not a pdf")
        assert isinstance(text, str)


# ---------------------------------------------------------------------------
# Tests: Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Test module-level constants."""

    def test_quality_threshold(self):
        """Quality threshold should be 70."""
        assert QUALITY_THRESHOLD == 70

    def test_max_auto_fix_retries(self):
        """Max auto-fix retries should be 1."""
        assert MAX_AUTO_FIX_RETRIES == 1
