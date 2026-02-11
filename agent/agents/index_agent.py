"""IndexAgent — 论文索引 Agent

翻译完成后，从翻译结果中提取论文结构化元数据（标题、领域、方法、关键词等），
存入 SQLite 数据库，供 RAG / Context Engineering 检索。

Requirements: 6.1
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from agent.base import BaseAgent
from agent.context import AgentContext
from agent.registry import agent_registry
from agent.tools.paper_repository import PaperMetadata, PaperRepository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM extraction prompt
# ---------------------------------------------------------------------------

_EXTRACT_METADATA_PROMPT = """\
你是一个学术论文分析专家。请从以下翻译后的论文内容中提取结构化信息。

返回严格的 JSON 格式（不要包含 markdown 代码块标记）：
{{
  "title": "英文标题",
  "title_zh": "中文标题",
  "authors": ["作者1", "作者2"],
  "abstract": "中文摘要（200字以内的精炼总结）",
  "domain": "领域（如: nlp, cv, rl, multimodal, systems, math, other）",
  "research_problem": "研究问题（一句话描述）",
  "methodology": "方法论（一句话描述核心方法）",
  "contributions": ["主要贡献1", "主要贡献2", "主要贡献3"],
  "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"],
  "base_models": ["使用或对比的模型/数据集"],
  "year": 2024,
  "venue": "发表会议或期刊（如有，否则空字符串）"
}}

规则：
1. domain 使用小写英文标签
2. keywords 包含中英文关键词，5-10 个
3. 如果无法确定某个字段，使用空字符串或空数组
4. year 如果无法确定，使用 null
5. 只返回 JSON，不要任何解释

论文内容：
---
{text}
---
"""


def _parse_metadata_json(response: str) -> dict:
    """从 LLM 响应中解析 JSON 元数据"""
    text = response.strip()

    # 去掉 markdown 代码块
    fence_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
    match = fence_pattern.search(text)
    if match:
        text = match.group(1).strip()

    # 找 JSON 对象
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
        return {}
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse metadata JSON: %s", text[:200])
        return {}


# ---------------------------------------------------------------------------
# Fallback metadata extraction (no LLM)
# ---------------------------------------------------------------------------

_TITLE_PATTERN = re.compile(r"^#\s+(.+)", re.MULTILINE)
_HEADING2_PATTERN = re.compile(r"^##\s+(.+)", re.MULTILINE)


def _extract_metadata_fallback(translated_md: str, ctx: AgentContext) -> PaperMetadata:
    """无 LLM 时的降级提取：从 Markdown 结构中提取基本信息"""
    meta = PaperMetadata()

    # 标题：第一个 # 标题
    title_match = _TITLE_PATTERN.search(translated_md)
    if title_match:
        meta.title_zh = title_match.group(1).strip()

    # 领域：从 prompt_profile 获取
    if ctx.prompt_profile and ctx.prompt_profile.domain:
        meta.domain = ctx.prompt_profile.domain

    # 关键词：从 glossary 的 key 中取前 10 个
    if ctx.glossary:
        meta.keywords = list(ctx.glossary.keys())[:10]

    # 摘要：取前 500 字符
    clean_text = re.sub(r"[#|*`\[\]()]", "", translated_md)
    meta.abstract = clean_text[:500].strip()

    return meta


# ---------------------------------------------------------------------------
# IndexAgent
# ---------------------------------------------------------------------------

@agent_registry.register
class IndexAgent(BaseAgent):
    """论文索引 Agent：提取元数据 → 存入 SQLite

    Workflow:
        1. 从翻译后的 Markdown 提取结构化元数据（LLM 或降级）
        2. 可选：生成摘要 embedding
        3. 存入 PaperRepository（SQLite）
        4. 写回 ctx.paper_metadata

    依赖:
        - ctx.translated_md: 翻译后的 Markdown（必须非空）
        - ctx.prompt_profile: 翻译配置（可选，用于补充领域信息）
        - ctx.glossary: 术语表（可选，用于补充关键词）
        - ctx.quality_report: 质量报告（可选，用于记录质量分）
    """

    def __init__(
        self,
        paper_repository: PaperRepository | None = None,
        translation_service: Any | None = None,
    ) -> None:
        """初始化 IndexAgent

        Args:
            paper_repository: 可选的 PaperRepository 实例（依赖注入）
            translation_service: 可选的 TranslationService 实例（依赖注入）
        """
        self._paper_repo = paper_repository
        self._translation_service = translation_service

    @property
    def name(self) -> str:
        return "index"

    @property
    def description(self) -> str:
        return "论文索引 Agent：提取元数据 → 存入数据库"

    async def _get_paper_repository(self) -> PaperRepository:
        if self._paper_repo is not None:
            return self._paper_repo
        repo = PaperRepository()
        await repo.init_db()
        self._paper_repo = repo
        return repo

    async def _get_translation_service(self) -> Any:
        if self._translation_service is not None:
            return self._translation_service
        from backend.app.services.translator import TranslationService
        self._translation_service = await TranslationService.from_manager()
        return self._translation_service

    async def run(self, input_data: AgentContext, **kwargs) -> AgentContext:
        ctx = input_data

        if not ctx.translated_md:
            logger.warning("IndexAgent: no translated_md, skipping indexing")
            await ctx.event_bus.publish(ctx.task_id, {
                "agent": "index",
                "stage": "skip",
                "progress": 91,
                "detail": {"message": "无翻译内容，跳过索引"},
            })
            return ctx

        # 1. 提取元数据
        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "index",
            "stage": "extracting",
            "progress": 91,
            "detail": {"message": "提取论文元数据..."},
        })

        metadata = await self._extract_metadata(ctx)

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "index",
            "stage": "extracting",
            "progress": 93,
            "detail": {
                "message": f"元数据提取完成: {metadata.title_zh or metadata.title} | 领域: {metadata.domain}",
                "domain": metadata.domain,
                "keywords": metadata.keywords,
            },
        })

        ctx.cancellation_token.check()

        # 2. 补充来自 ctx 的信息
        metadata = self._enrich_metadata(metadata, ctx)

        # 3. 生成 embedding（可选）
        embedding = await self._generate_embedding(metadata)

        # 4. 存入数据库
        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "index",
            "stage": "saving_db",
            "progress": 95,
            "detail": {"message": "写入论文数据库..."},
        })

        quality_score = ctx.quality_report.score if ctx.quality_report else None
        repo = await self._get_paper_repository()
        await repo.upsert(
            paper_id=ctx.task_id,
            metadata=metadata,
            embedding=embedding,
            quality_score=quality_score,
            filename=ctx.filename,
        )

        # 5. 写回 ctx
        ctx.paper_metadata = metadata.to_dict()

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "index",
            "stage": "complete",
            "progress": 96,
            "detail": {
                "message": f"索引完成: {metadata.domain} | {len(metadata.keywords)} 关键词",
                "paper_id": ctx.task_id,
            },
        })

        logger.info(
            "IndexAgent complete: id=%s, domain=%s, keywords=%d",
            ctx.task_id, metadata.domain, len(metadata.keywords),
        )

        return ctx

    # ------------------------------------------------------------------
    # Metadata extraction
    # ------------------------------------------------------------------

    async def _extract_metadata(self, ctx: AgentContext) -> PaperMetadata:
        """用 LLM 提取元数据，失败时降级为规则提取"""
        try:
            svc = await self._get_translation_service()

            # 截取前 8000 字符（摘要 + 引言 + 方法部分）
            text = ctx.translated_md[:8000]
            prompt = _EXTRACT_METADATA_PROMPT.format(text=text)

            response = await svc.translate(
                text=prompt,
                system_prompt="你是学术论文分析助手。只返回有效 JSON。",
            )

            raw = _parse_metadata_json(response)
            if raw:
                metadata = PaperMetadata.from_dict(raw)
                logger.info("LLM metadata extraction succeeded: %s", metadata.title)
                return metadata
            else:
                logger.warning("LLM returned empty metadata, falling back")
                return _extract_metadata_fallback(ctx.translated_md, ctx)

        except Exception as e:
            logger.warning("LLM metadata extraction failed: %s, using fallback", e)
            return _extract_metadata_fallback(ctx.translated_md, ctx)

    def _enrich_metadata(self, metadata: PaperMetadata, ctx: AgentContext) -> PaperMetadata:
        """用 ctx 中已有的信息补充元数据"""
        # 从 prompt_profile 补充领域
        if not metadata.domain and ctx.prompt_profile and ctx.prompt_profile.domain:
            metadata.domain = ctx.prompt_profile.domain

        # 从 glossary 补充关键词
        if ctx.glossary and len(metadata.keywords) < 5:
            existing = set(metadata.keywords)
            for term in list(ctx.glossary.keys())[:10]:
                if term not in existing:
                    metadata.keywords.append(term)
                    existing.add(term)
                if len(metadata.keywords) >= 10:
                    break

        return metadata

    # ------------------------------------------------------------------
    # Embedding generation
    # ------------------------------------------------------------------

    async def _generate_embedding(self, metadata: PaperMetadata) -> list[float] | None:
        """生成摘要的 embedding 向量（可选）

        当前返回 None，后续可接入 embedding 模型。
        """
        # TODO: 接入 embedding 模型（如 text-embedding-3-small 或 multilingual-e5）
        # text = f"{metadata.title} {metadata.abstract} {metadata.research_problem}"
        # embedding = await embedding_service.encode(text)
        # return embedding
        return None
