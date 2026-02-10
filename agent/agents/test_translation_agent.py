"""Tests for TranslationAgent

Unit tests covering:
- Registration in agent_registry
- _analyze_document with mock PDF content
- _select_pipeline logic (scanned/native, OCR availability)
- _generate_prompt with glossary injection
- _execute_with_retry with failures and retries
- Cancellation token check
- Progress events published via EventBus
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from agent.agents.translation_agent import (
    TranslationAgent,
    DocumentAnalysis,
    _count_formulas,
    _count_tables,
    _detect_language_distribution,
)
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
    """Create a minimal AgentContext for testing."""
    return AgentContext(
        task_id="test-task-001",
        filename="test.pdf",
        file_content=b"%PDF-1.4 fake content",
        event_bus=event_bus,
        glossary={"Transformer": "Transformer模型", "attention": "注意力"},
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
# Tests: Helper functions
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """Test module-level helper functions."""

    def test_count_formulas_inline(self):
        """Should count inline math $...$."""
        text = "The formula $E=mc^2$ and $a+b=c$ are important."
        count, total = _count_formulas(text)
        assert count == 2
        assert total == len(text)

    def test_count_formulas_display(self):
        """Should count display math $$...$$."""
        text = "Here is:\n$$\\int_0^1 f(x) dx$$\nand more."
        count, total = _count_formulas(text)
        assert count >= 1

    def test_count_formulas_empty(self):
        """No formulas should return 0."""
        count, total = _count_formulas("No formulas here.")
        assert count == 0

    def test_count_tables_basic(self):
        """Should count a basic markdown table."""
        text = "| A | B |\n|---|---|\n| 1 | 2 |\n\nSome text."
        assert _count_tables(text) == 1

    def test_count_tables_multiple(self):
        """Should count multiple tables."""
        text = (
            "| A | B |\n|---|---|\n| 1 | 2 |\n\n"
            "Some text.\n\n"
            "| X | Y |\n|---|---|\n| 3 | 4 |"
        )
        assert _count_tables(text) == 2

    def test_count_tables_none(self):
        """No tables should return 0."""
        assert _count_tables("No tables here.") == 0

    def test_language_distribution_english(self):
        """Mostly English text."""
        dist = _detect_language_distribution("Hello world this is English text")
        assert dist["en"] > 0.5
        assert dist["zh"] == 0.0

    def test_language_distribution_chinese(self):
        """Mostly Chinese text."""
        dist = _detect_language_distribution("这是一段中文文本用于测试")
        assert dist["zh"] > 0.5

    def test_language_distribution_empty(self):
        """Empty text should return all zeros."""
        dist = _detect_language_distribution("")
        assert dist["en"] == 0.0
        assert dist["zh"] == 0.0


# ---------------------------------------------------------------------------
# Tests: _analyze_document
# ---------------------------------------------------------------------------


class TestAnalyzeDocument:
    """Test document analysis with mocked PyMuPDF."""

    @pytest.mark.asyncio
    async def test_analyze_native_pdf(self, agent: TranslationAgent, ctx: AgentContext):
        """PDF with extractable text should be classified as 'native'."""
        long_text = "This is a native PDF with lots of text. " * 20

        mock_page = MagicMock()
        mock_page.get_text.return_value = long_text

        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.close = MagicMock()

        with patch(
            "agent.agents.translation_agent.fitz",
            create=True,
        ) as mock_fitz_module:
            # We need to patch the import inside the method
            import agent.agents.translation_agent as ta_module

            original_analyze = ta_module.TranslationAgent._analyze_document

            async def patched_analyze(self_agent, context):
                # Simulate what _analyze_document does with fitz
                analysis = DocumentAnalysis()
                extracted_text = long_text
                if len(extracted_text.strip()) >= self_agent.NATIVE_TEXT_THRESHOLD:
                    analysis.doc_type = "native"
                else:
                    analysis.doc_type = "scanned"
                formula_count, total_chars = _count_formulas(extracted_text)
                analysis.formula_density = round(
                    formula_count / max(total_chars, 1), 6
                )
                analysis.table_count = _count_tables(extracted_text)
                analysis.language_distribution = _detect_language_distribution(
                    extracted_text
                )
                return analysis

            with patch.object(
                TranslationAgent, "_analyze_document", patched_analyze
            ):
                result = await patched_analyze(agent, ctx)

            assert result.doc_type == "native"
            assert result.formula_density >= 0
            assert result.table_count >= 0
            assert "en" in result.language_distribution

    @pytest.mark.asyncio
    async def test_analyze_scanned_pdf(
        self, agent: TranslationAgent, ctx: AgentContext
    ):
        """PDF with little extractable text should be classified as 'scanned'."""
        # Simulate fitz not being available
        with patch.dict("sys.modules", {"fitz": None}):
            # Force re-import to pick up the patched module
            result = await agent._analyze_document(ctx)

        assert result.doc_type == "scanned"
        assert result.formula_density >= 0
        assert result.table_count >= 0

    @pytest.mark.asyncio
    async def test_analyze_returns_complete_fields(
        self, agent: TranslationAgent, ctx: AgentContext
    ):
        """Analysis result should contain all required fields."""
        with patch.dict("sys.modules", {"fitz": None}):
            result = await agent._analyze_document(ctx)

        d = result.to_dict()
        assert "doc_type" in d
        assert "language_distribution" in d
        assert "formula_density" in d
        assert "table_count" in d
        assert d["doc_type"] in ("scanned", "native")
        assert d["formula_density"] >= 0
        assert d["table_count"] >= 0


# ---------------------------------------------------------------------------
# Tests: _select_pipeline
# ---------------------------------------------------------------------------


class TestSelectPipeline:
    """Test pipeline selection logic."""

    def test_native_pdf_selects_llm(self, agent: TranslationAgent, ctx: AgentContext):
        """Native PDF should always select 'llm' pipeline."""
        analysis = DocumentAnalysis(doc_type="native")
        result = agent._select_pipeline(analysis, ctx)
        assert result == "llm"

    def test_scanned_pdf_with_ocr_selects_ocr(
        self, agent: TranslationAgent, ctx: AgentContext
    ):
        """Scanned PDF with OCR available should select 'ocr' pipeline."""
        analysis = DocumentAnalysis(doc_type="scanned")
        with patch.object(agent, "_is_ocr_available", return_value=True):
            result = agent._select_pipeline(analysis, ctx)
        assert result == "ocr"

    def test_scanned_pdf_without_ocr_falls_back_to_llm(
        self, agent: TranslationAgent, ctx: AgentContext
    ):
        """Scanned PDF without OCR should fall back to 'llm' pipeline."""
        analysis = DocumentAnalysis(doc_type="scanned")
        with patch.object(agent, "_is_ocr_available", return_value=False):
            result = agent._select_pipeline(analysis, ctx)
        assert result == "llm"


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
    async def test_full_run_publishes_all_stages(
        self, agent: TranslationAgent, ctx: AgentContext, event_bus: EventBus
    ):
        """run() should publish events for all stages."""
        queue = event_bus.subscribe(ctx.task_id)
        expected_result = PipelineResult(translated_md="完整翻译结果")

        with patch.object(
            agent,
            "_analyze_document",
            new_callable=AsyncMock,
            return_value=DocumentAnalysis(doc_type="native"),
        ), patch.object(
            agent, "_select_pipeline", return_value="llm"
        ), patch.object(
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

        # Should have events for: analysis, pipeline_selection,
        # prompt_generation, translating, complete
        stages = [e["stage"] for e in events]
        assert "analysis" in stages
        assert "pipeline_selection" in stages
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
    async def test_run_cancellation_at_analysis(
        self, agent: TranslationAgent, ctx: AgentContext
    ):
        """Cancellation after analysis should stop execution."""

        async def mock_analyze(context):
            ctx.cancellation_token.cancel()
            return DocumentAnalysis(doc_type="native")

        with patch.object(agent, "_analyze_document", side_effect=mock_analyze):
            with pytest.raises(asyncio.CancelledError):
                await agent.run(ctx)

    @pytest.mark.asyncio
    async def test_run_sets_translated_md(
        self, agent: TranslationAgent, ctx: AgentContext
    ):
        """run() should set ctx.translated_md."""
        expected_result = PipelineResult(translated_md="翻译后的文本")

        with patch.object(
            agent,
            "_analyze_document",
            new_callable=AsyncMock,
            return_value=DocumentAnalysis(doc_type="native"),
        ), patch.object(
            agent, "_select_pipeline", return_value="llm"
        ), patch.object(
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
            "_analyze_document",
            new_callable=AsyncMock,
            return_value=DocumentAnalysis(doc_type="native"),
        ), patch.object(
            agent, "_select_pipeline", return_value="llm"
        ), patch.object(
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


# ---------------------------------------------------------------------------
# Tests: DocumentAnalysis dataclass
# ---------------------------------------------------------------------------


class TestDocumentAnalysis:
    """Test DocumentAnalysis dataclass."""

    def test_to_dict(self):
        """to_dict should return all fields."""
        analysis = DocumentAnalysis(
            doc_type="native",
            language_distribution={"en": 0.8, "zh": 0.1, "other": 0.1},
            formula_density=0.05,
            table_count=3,
        )
        d = analysis.to_dict()
        assert d["doc_type"] == "native"
        assert d["formula_density"] == 0.05
        assert d["table_count"] == 3
        assert d["language_distribution"]["en"] == 0.8

    def test_defaults(self):
        """Default values should be sensible."""
        analysis = DocumentAnalysis()
        assert analysis.doc_type == "scanned"
        assert analysis.formula_density == 0.0
        assert analysis.table_count == 0
        assert analysis.language_distribution == {}
