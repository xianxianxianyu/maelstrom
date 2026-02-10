"""Tests for OCRAgent"""
from __future__ import annotations
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import pytest
import pytest_asyncio

from agent.agents.ocr_agent import (
    OCRAgent, DocumentAnalysis, _count_formulas, _count_tables,
    _detect_language_distribution, _count_columns,
)
from agent.context import AgentContext
from agent.event_bus import EventBus
from agent.registry import agent_registry


@pytest_asyncio.fixture
async def event_bus():
    return EventBus()

@pytest_asyncio.fixture
async def ctx(event_bus):
    return AgentContext(
        task_id="test-ocr-001", filename="test.pdf",
        file_content=b"%PDF-1.4 fake", event_bus=event_bus,
    )

@pytest.fixture
def agent():
    return OCRAgent()


class TestRegistration:
    def test_registered_in_registry(self):
        assert agent_registry.get("OCRAgent") is OCRAgent

    def test_name_property(self, agent):
        assert agent.name == "ocr"

    def test_description_property(self, agent):
        assert agent.description


class TestHelperFunctions:
    def test_count_formulas(self):
        count, total = _count_formulas("No formulas here.")
        assert count >= 0

    def test_count_tables(self):
        text = "| A | B |\n|---|---|\n| 1 | 2 |"
        assert _count_tables(text) == 1

    def test_detect_language_english(self):
        dist = _detect_language_distribution("This is English text.")
        assert dist["en"] > 0.5

    def test_count_columns(self):
        assert _count_columns("| A | B | C |") == 3


class TestRunFlow:
    @pytest.mark.asyncio
    async def test_run_sets_pipeline_type(self, agent, ctx):
        with patch.object(agent, "_analyze_document", new_callable=AsyncMock) as m1:
            with patch.object(agent, "_run_llm_parse", new_callable=AsyncMock):
                m1.return_value = DocumentAnalysis(doc_type="native")
                await agent.run(ctx)
        assert ctx.pipeline_type == "llm"

    @pytest.mark.asyncio
    async def test_run_skips_on_rerun(self, agent, ctx):
        ctx.pipeline_type = "llm"
        ctx.parsed_pdf = MagicMock()
        with patch.object(agent, "_analyze_document", new_callable=AsyncMock) as m1:
            await agent.run(ctx)
        m1.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_respects_cancellation(self, agent, ctx):
        ctx.cancellation_token.cancel()
        with pytest.raises(asyncio.CancelledError):
            await agent.run(ctx)
