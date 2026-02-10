"""Tests for translation_workflow — 翻译工作流入口

Unit tests covering:
- OrchestratorAgent is called with correct AgentContext
- Result dict format
- Auto-generated task_id
- Custom task_id
- CancellationToken passed through
- Error handling
- Dependency injection for OrchestratorAgent
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from agent.context import AgentContext
from agent.event_bus import EventBus
from agent.models import QualityReport
from agent.workflows.translation_workflow import run_translation_workflow
from backend.app.services.pipelines.base import CancellationToken


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_quality_report(score: int = 85) -> QualityReport:
    """Create a QualityReport with the given score."""
    return QualityReport(
        score=score,
        suggestions=["建议1"],
        timestamp="2024-01-01T00:00:00+00:00",
    )


def _make_mock_orchestrator(
    translated_md: str = "翻译后的文本",
    quality_score: int = 85,
    glossary: dict[str, str] | None = None,
):
    """Create a mock OrchestratorAgent that populates the context."""
    agent = AsyncMock()

    async def run_side_effect(ctx, **kwargs):
        ctx.translated_md = translated_md
        ctx.quality_report = _make_quality_report(quality_score)
        ctx.glossary = glossary or {"Transformer": "变换器"}
        return ctx

    agent.side_effect = run_side_effect
    return agent


# ---------------------------------------------------------------------------
# Tests: Result Dict Format
# ---------------------------------------------------------------------------


class TestResultFormat:
    """Test that the result dict has the expected format."""

    @pytest.mark.asyncio
    async def test_result_contains_required_keys(self):
        """Result should contain task_id, translated_md, quality_report, glossary."""
        mock_orch = _make_mock_orchestrator()

        result = await run_translation_workflow(
            file_content=b"%PDF-1.4 fake",
            filename="test.pdf",
            orchestrator_agent=mock_orch,
        )

        assert "task_id" in result
        assert "translated_md" in result
        assert "quality_report" in result
        assert "glossary" in result

    @pytest.mark.asyncio
    async def test_result_translated_md(self):
        """Result translated_md should match what OrchestratorAgent produced."""
        mock_orch = _make_mock_orchestrator(translated_md="翻译结果ABC")

        result = await run_translation_workflow(
            file_content=b"%PDF-1.4 fake",
            filename="test.pdf",
            orchestrator_agent=mock_orch,
        )

        assert result["translated_md"] == "翻译结果ABC"

    @pytest.mark.asyncio
    async def test_result_quality_report_is_dict(self):
        """Result quality_report should be a serialized dict (not QualityReport object)."""
        mock_orch = _make_mock_orchestrator(quality_score=90)

        result = await run_translation_workflow(
            file_content=b"%PDF-1.4 fake",
            filename="test.pdf",
            orchestrator_agent=mock_orch,
        )

        qr = result["quality_report"]
        assert isinstance(qr, dict)
        assert qr["score"] == 90

    @pytest.mark.asyncio
    async def test_result_quality_report_none_when_not_set(self):
        """Result quality_report should be None if OrchestratorAgent didn't set it."""
        agent = AsyncMock()

        async def run_side_effect(ctx, **kwargs):
            ctx.translated_md = "翻译结果"
            # quality_report stays None
            return ctx

        agent.side_effect = run_side_effect

        result = await run_translation_workflow(
            file_content=b"%PDF-1.4 fake",
            filename="test.pdf",
            orchestrator_agent=agent,
        )

        assert result["quality_report"] is None

    @pytest.mark.asyncio
    async def test_result_glossary(self):
        """Result glossary should match what OrchestratorAgent produced."""
        mock_orch = _make_mock_orchestrator(
            glossary={"attention": "注意力", "Transformer": "变换器"}
        )

        result = await run_translation_workflow(
            file_content=b"%PDF-1.4 fake",
            filename="test.pdf",
            orchestrator_agent=mock_orch,
        )

        assert result["glossary"] == {"attention": "注意力", "Transformer": "变换器"}


# ---------------------------------------------------------------------------
# Tests: Task ID
# ---------------------------------------------------------------------------


class TestTaskId:
    """Test task_id generation and passthrough."""

    @pytest.mark.asyncio
    async def test_auto_generated_task_id(self):
        """When task_id is not provided, it should be auto-generated."""
        mock_orch = _make_mock_orchestrator()

        result = await run_translation_workflow(
            file_content=b"%PDF-1.4 fake",
            filename="test.pdf",
            orchestrator_agent=mock_orch,
        )

        assert result["task_id"] is not None
        assert isinstance(result["task_id"], str)
        assert len(result["task_id"]) == 8  # uuid hex[:8]

    @pytest.mark.asyncio
    async def test_custom_task_id(self):
        """When task_id is provided, it should be used as-is."""
        mock_orch = _make_mock_orchestrator()

        result = await run_translation_workflow(
            file_content=b"%PDF-1.4 fake",
            filename="test.pdf",
            task_id="my-custom-id",
            orchestrator_agent=mock_orch,
        )

        assert result["task_id"] == "my-custom-id"

    @pytest.mark.asyncio
    async def test_two_calls_generate_different_task_ids(self):
        """Two calls without task_id should generate different IDs."""
        mock_orch1 = _make_mock_orchestrator()
        mock_orch2 = _make_mock_orchestrator()

        result1 = await run_translation_workflow(
            file_content=b"%PDF-1.4 fake",
            filename="test.pdf",
            orchestrator_agent=mock_orch1,
        )
        result2 = await run_translation_workflow(
            file_content=b"%PDF-1.4 fake",
            filename="test.pdf",
            orchestrator_agent=mock_orch2,
        )

        assert result1["task_id"] != result2["task_id"]


# ---------------------------------------------------------------------------
# Tests: OrchestratorAgent Called Correctly
# ---------------------------------------------------------------------------


class TestOrchestratorCalled:
    """Test that OrchestratorAgent is called with correct AgentContext."""

    @pytest.mark.asyncio
    async def test_orchestrator_called_once(self):
        """OrchestratorAgent should be called exactly once."""
        mock_orch = _make_mock_orchestrator()

        await run_translation_workflow(
            file_content=b"%PDF-1.4 fake",
            filename="test.pdf",
            orchestrator_agent=mock_orch,
        )

        mock_orch.assert_called_once()

    @pytest.mark.asyncio
    async def test_orchestrator_receives_agent_context(self):
        """OrchestratorAgent should receive an AgentContext instance."""
        mock_orch = _make_mock_orchestrator()

        await run_translation_workflow(
            file_content=b"%PDF-1.4 fake",
            filename="test.pdf",
            task_id="ctx-test-001",
            orchestrator_agent=mock_orch,
        )

        call_args = mock_orch.call_args
        ctx = call_args[0][0]  # first positional arg
        assert isinstance(ctx, AgentContext)

    @pytest.mark.asyncio
    async def test_context_has_correct_filename(self):
        """AgentContext should have the correct filename."""
        mock_orch = _make_mock_orchestrator()

        await run_translation_workflow(
            file_content=b"%PDF-1.4 fake",
            filename="paper.pdf",
            orchestrator_agent=mock_orch,
        )

        ctx = mock_orch.call_args[0][0]
        assert ctx.filename == "paper.pdf"

    @pytest.mark.asyncio
    async def test_context_has_correct_file_content(self):
        """AgentContext should have the correct file_content."""
        content = b"%PDF-1.4 test content bytes"
        mock_orch = _make_mock_orchestrator()

        await run_translation_workflow(
            file_content=content,
            filename="test.pdf",
            orchestrator_agent=mock_orch,
        )

        ctx = mock_orch.call_args[0][0]
        assert ctx.file_content == content

    @pytest.mark.asyncio
    async def test_context_has_correct_task_id(self):
        """AgentContext should have the provided task_id."""
        mock_orch = _make_mock_orchestrator()

        await run_translation_workflow(
            file_content=b"%PDF-1.4 fake",
            filename="test.pdf",
            task_id="my-task-123",
            orchestrator_agent=mock_orch,
        )

        ctx = mock_orch.call_args[0][0]
        assert ctx.task_id == "my-task-123"

    @pytest.mark.asyncio
    async def test_context_has_event_bus(self):
        """AgentContext should have an EventBus instance."""
        mock_orch = _make_mock_orchestrator()

        await run_translation_workflow(
            file_content=b"%PDF-1.4 fake",
            filename="test.pdf",
            orchestrator_agent=mock_orch,
        )

        ctx = mock_orch.call_args[0][0]
        assert ctx.event_bus is not None


# ---------------------------------------------------------------------------
# Tests: CancellationToken
# ---------------------------------------------------------------------------


class TestCancellationToken:
    """Test CancellationToken passthrough."""

    @pytest.mark.asyncio
    async def test_custom_cancellation_token_passed(self):
        """Custom CancellationToken should be passed to AgentContext."""
        token = CancellationToken()
        mock_orch = _make_mock_orchestrator()

        await run_translation_workflow(
            file_content=b"%PDF-1.4 fake",
            filename="test.pdf",
            cancellation_token=token,
            orchestrator_agent=mock_orch,
        )

        ctx = mock_orch.call_args[0][0]
        assert ctx.cancellation_token is token

    @pytest.mark.asyncio
    async def test_default_cancellation_token_created(self):
        """When no CancellationToken is provided, a default should be created."""
        mock_orch = _make_mock_orchestrator()

        await run_translation_workflow(
            file_content=b"%PDF-1.4 fake",
            filename="test.pdf",
            orchestrator_agent=mock_orch,
        )

        ctx = mock_orch.call_args[0][0]
        assert isinstance(ctx.cancellation_token, CancellationToken)
        assert not ctx.cancellation_token.is_cancelled


# ---------------------------------------------------------------------------
# Tests: Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Test error propagation from OrchestratorAgent."""

    @pytest.mark.asyncio
    async def test_orchestrator_error_propagates(self):
        """Errors from OrchestratorAgent should propagate to caller."""
        agent = AsyncMock(side_effect=RuntimeError("Orchestrator failed"))

        with pytest.raises(RuntimeError, match="Orchestrator failed"):
            await run_translation_workflow(
                file_content=b"%PDF-1.4 fake",
                filename="test.pdf",
                orchestrator_agent=agent,
            )

    @pytest.mark.asyncio
    async def test_cancellation_error_propagates(self):
        """CancelledError from OrchestratorAgent should propagate."""
        agent = AsyncMock(side_effect=asyncio.CancelledError("cancelled"))

        with pytest.raises(asyncio.CancelledError):
            await run_translation_workflow(
                file_content=b"%PDF-1.4 fake",
                filename="test.pdf",
                orchestrator_agent=agent,
            )


# ---------------------------------------------------------------------------
# Tests: Dependency Injection
# ---------------------------------------------------------------------------


class TestDependencyInjection:
    """Test that OrchestratorAgent can be injected or created from registry."""

    @pytest.mark.asyncio
    async def test_injected_orchestrator_used(self):
        """When orchestrator_agent is provided, it should be used directly."""
        mock_orch = _make_mock_orchestrator()

        await run_translation_workflow(
            file_content=b"%PDF-1.4 fake",
            filename="test.pdf",
            orchestrator_agent=mock_orch,
        )

        mock_orch.assert_called_once()

    @pytest.mark.asyncio
    async def test_registry_used_when_no_injection(self):
        """When orchestrator_agent is not provided, registry.create should be used."""
        mock_orch = _make_mock_orchestrator()

        with patch(
            "agent.workflows.translation_workflow.agent_registry"
        ) as mock_registry:
            mock_registry.create.return_value = mock_orch

            result = await run_translation_workflow(
                file_content=b"%PDF-1.4 fake",
                filename="test.pdf",
            )

            mock_registry.create.assert_called_once_with("OrchestratorAgent")
            assert result["translated_md"] == "翻译后的文本"
