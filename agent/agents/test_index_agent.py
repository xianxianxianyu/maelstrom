"""Unit tests for IndexAgent — 论文索引 Agent"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.agents.index_agent import (
    IndexAgent,
    _extract_metadata_fallback,
    _parse_metadata_json,
)
from agent.context import AgentContext
from agent.tools.paper_repository import PaperMetadata, PaperRepository
from backend.app.services.pipelines.base import CancellationToken
from backend.app.services.prompt_generator import PromptProfile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeEventBus:
    def __init__(self):
        self.events = []

    async def publish(self, task_id, event):
        self.events.append(event)


def _make_ctx(
    translated_md: str = "# Test Paper\n\n这是一篇测试论文。",
    glossary: dict | None = None,
    prompt_profile: PromptProfile | None = None,
) -> AgentContext:
    bus = FakeEventBus()
    ctx = AgentContext(
        task_id="test-001",
        filename="paper.pdf",
        file_content=b"fake-pdf",
        event_bus=bus,
        cancellation_token=CancellationToken(),
    )
    ctx.translated_md = translated_md
    if glossary:
        ctx.glossary = glossary
    if prompt_profile:
        ctx.prompt_profile = prompt_profile
    return ctx


class FakeRepo:
    """Mock PaperRepository"""
    def __init__(self):
        self.upserted = []

    async def init_db(self):
        pass

    async def upsert(self, paper_id, metadata, embedding=None, quality_score=None, filename=""):
        self.upserted.append({
            "paper_id": paper_id,
            "metadata": metadata,
            "embedding": embedding,
            "quality_score": quality_score,
            "filename": filename,
        })

    async def close(self):
        pass


class FakeTranslationService:
    """Mock TranslationService that returns structured JSON"""
    def __init__(self, response: str = ""):
        self._response = response

    async def translate(self, text: str, system_prompt: str = "") -> str:
        return self._response


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_name_property(self):
        agent = IndexAgent()
        assert agent.name == "index"

    def test_description_property(self):
        agent = IndexAgent()
        assert "索引" in agent.description


# ---------------------------------------------------------------------------
# _parse_metadata_json tests
# ---------------------------------------------------------------------------

class TestParseMetadataJson:
    def test_valid_json(self):
        raw = '{"title": "Test", "domain": "nlp"}'
        result = _parse_metadata_json(raw)
        assert result["title"] == "Test"

    def test_json_in_markdown_fence(self):
        raw = '```json\n{"title": "Test"}\n```'
        result = _parse_metadata_json(raw)
        assert result["title"] == "Test"

    def test_json_with_surrounding_text(self):
        raw = 'Here is the result:\n{"title": "Test"}\nDone.'
        result = _parse_metadata_json(raw)
        assert result["title"] == "Test"

    def test_invalid_json(self):
        result = _parse_metadata_json("not json at all")
        assert result == {}

    def test_empty_string(self):
        result = _parse_metadata_json("")
        assert result == {}

    def test_array_returns_empty(self):
        # 纯数组（无内嵌对象）返回空
        result = _parse_metadata_json('[1, 2, 3]')
        assert result == {}


# ---------------------------------------------------------------------------
# _extract_metadata_fallback tests
# ---------------------------------------------------------------------------

class TestExtractMetadataFallback:
    def test_extracts_title_from_heading(self):
        md = "# Attention Is All You Need\n\n这是正文。"
        ctx = _make_ctx(translated_md=md)
        meta = _extract_metadata_fallback(md, ctx)
        assert meta.title_zh == "Attention Is All You Need"

    def test_extracts_domain_from_profile(self):
        profile = PromptProfile(domain="nlp")
        ctx = _make_ctx(prompt_profile=profile)
        meta = _extract_metadata_fallback(ctx.translated_md, ctx)
        assert meta.domain == "nlp"

    def test_extracts_keywords_from_glossary(self):
        ctx = _make_ctx(glossary={"attention": "注意力", "transformer": "Transformer"})
        meta = _extract_metadata_fallback(ctx.translated_md, ctx)
        assert "attention" in meta.keywords
        assert "transformer" in meta.keywords

    def test_extracts_abstract(self):
        md = "# Title\n\n这是一段很长的摘要文本，用于测试提取功能。"
        ctx = _make_ctx(translated_md=md)
        meta = _extract_metadata_fallback(md, ctx)
        assert len(meta.abstract) > 0

    def test_empty_md(self):
        ctx = _make_ctx(translated_md="")
        meta = _extract_metadata_fallback("", ctx)
        assert meta.title_zh == ""


# ---------------------------------------------------------------------------
# IndexAgent.run tests
# ---------------------------------------------------------------------------

class TestIndexAgentRun:
    @pytest.mark.asyncio
    async def test_run_with_llm_extraction(self):
        """LLM 成功提取元数据"""
        llm_response = json.dumps({
            "title": "Attention Is All You Need",
            "title_zh": "注意力机制就是你所需要的",
            "authors": ["Vaswani"],
            "abstract": "本文提出 Transformer",
            "domain": "nlp",
            "research_problem": "序列建模",
            "methodology": "自注意力",
            "contributions": ["提出 Transformer"],
            "keywords": ["attention", "transformer"],
            "base_models": ["WMT"],
            "year": 2017,
            "venue": "NeurIPS",
        }, ensure_ascii=False)

        repo = FakeRepo()
        svc = FakeTranslationService(response=llm_response)
        agent = IndexAgent(paper_repository=repo, translation_service=svc)

        ctx = _make_ctx()
        result = await agent.run(ctx)

        assert len(repo.upserted) == 1
        assert repo.upserted[0]["paper_id"] == "test-001"
        assert repo.upserted[0]["metadata"].domain == "nlp"
        assert result.paper_metadata["title"] == "Attention Is All You Need"

    @pytest.mark.asyncio
    async def test_run_fallback_on_llm_failure(self):
        """LLM 失败时降级为规则提取"""
        svc = FakeTranslationService(response="invalid json response")
        repo = FakeRepo()
        agent = IndexAgent(paper_repository=repo, translation_service=svc)

        ctx = _make_ctx(
            translated_md="# My Paper\n\n这是正文内容。",
            prompt_profile=PromptProfile(domain="cv"),
        )
        result = await agent.run(ctx)

        assert len(repo.upserted) == 1
        meta = repo.upserted[0]["metadata"]
        assert meta.domain == "cv"  # 从 prompt_profile 获取
        assert result.paper_metadata is not None

    @pytest.mark.asyncio
    async def test_run_skips_when_no_translated_md(self):
        """无翻译内容时跳过索引"""
        repo = FakeRepo()
        agent = IndexAgent(paper_repository=repo)

        ctx = _make_ctx(translated_md="")
        result = await agent.run(ctx)

        assert len(repo.upserted) == 0
        # 检查发布了 skip 事件
        events = ctx.event_bus.events
        assert any(e.get("stage") == "skip" for e in events)

    @pytest.mark.asyncio
    async def test_run_publishes_sse_events(self):
        """验证 SSE 事件发布"""
        llm_response = json.dumps({
            "title": "Test",
            "domain": "nlp",
            "keywords": ["test"],
        })
        repo = FakeRepo()
        svc = FakeTranslationService(response=llm_response)
        agent = IndexAgent(paper_repository=repo, translation_service=svc)

        ctx = _make_ctx()
        await agent.run(ctx)

        events = ctx.event_bus.events
        agents = [e.get("agent") for e in events]
        stages = [e.get("stage") for e in events]

        assert all(a == "index" for a in agents)
        assert "extracting" in stages
        assert "saving_db" in stages
        assert "complete" in stages

    @pytest.mark.asyncio
    async def test_run_enriches_keywords_from_glossary(self):
        """从 glossary 补充关键词"""
        llm_response = json.dumps({
            "title": "Test",
            "domain": "nlp",
            "keywords": ["attention"],
        })
        repo = FakeRepo()
        svc = FakeTranslationService(response=llm_response)
        agent = IndexAgent(paper_repository=repo, translation_service=svc)

        ctx = _make_ctx(glossary={"transformer": "Transformer", "bert": "BERT"})
        await agent.run(ctx)

        meta = repo.upserted[0]["metadata"]
        assert "transformer" in meta.keywords
        assert "bert" in meta.keywords

    @pytest.mark.asyncio
    async def test_run_records_quality_score(self):
        """记录质量分"""
        from agent.models import QualityReport

        llm_response = json.dumps({"title": "Test", "domain": "nlp"})
        repo = FakeRepo()
        svc = FakeTranslationService(response=llm_response)
        agent = IndexAgent(paper_repository=repo, translation_service=svc)

        ctx = _make_ctx()
        ctx.quality_report = QualityReport(score=85)
        await agent.run(ctx)

        assert repo.upserted[0]["quality_score"] == 85

    @pytest.mark.asyncio
    async def test_run_records_filename(self):
        """记录文件名"""
        llm_response = json.dumps({"title": "Test", "domain": "nlp"})
        repo = FakeRepo()
        svc = FakeTranslationService(response=llm_response)
        agent = IndexAgent(paper_repository=repo, translation_service=svc)

        ctx = _make_ctx()
        await agent.run(ctx)

        assert repo.upserted[0]["filename"] == "paper.pdf"

    @pytest.mark.asyncio
    async def test_progress_values_in_range(self):
        """进度值在 91-96 范围内"""
        llm_response = json.dumps({"title": "Test", "domain": "nlp"})
        repo = FakeRepo()
        svc = FakeTranslationService(response=llm_response)
        agent = IndexAgent(paper_repository=repo, translation_service=svc)

        ctx = _make_ctx()
        await agent.run(ctx)

        for event in ctx.event_bus.events:
            p = event.get("progress", 0)
            assert 91 <= p <= 96, f"Progress {p} out of range [91, 96]"


# ---------------------------------------------------------------------------
# IndexAgent embedding tests
# ---------------------------------------------------------------------------

class TestIndexAgentEmbedding:
    @pytest.mark.asyncio
    async def test_embedding_is_none_by_default(self):
        """当前 embedding 返回 None（TODO）"""
        llm_response = json.dumps({"title": "Test", "domain": "nlp"})
        repo = FakeRepo()
        svc = FakeTranslationService(response=llm_response)
        agent = IndexAgent(paper_repository=repo, translation_service=svc)

        ctx = _make_ctx()
        await agent.run(ctx)

        assert repo.upserted[0]["embedding"] is None
