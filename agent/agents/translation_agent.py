"""TranslationAgent — 智能翻译 Agent

从 AgentContext 读取 OCRAgent 已解析的数据，生成 Prompt，执行翻译（带重试）。
每个阶段通过 AgentContext.event_bus 推送进度事件。

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 1.8
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

from agent.base import BaseAgent
from agent.context import AgentContext
from agent.registry import agent_registry
from backend.app.services.pipelines.base import PipelineResult

logger = logging.getLogger(__name__)


@agent_registry.register
class TranslationAgent(BaseAgent):
    """智能翻译 Agent：生成 Prompt → 执行翻译

    前置条件：OCRAgent 已填充 ctx.pipeline_type 和 ctx.parsed_pdf / ctx.ocr_md。

    Workflow:
        1. _generate_prompt: 注入术语表生成翻译 prompt
        2. _execute_with_retry: 带重试的翻译执行（最多 3 次）

    每个阶段通过 AgentContext.event_bus 推送进度事件。
    """

    def __init__(
        self,
        ocr_tool: Any | None = None,
        translate_tool: Any | None = None,
    ) -> None:
        self._ocr_tool = ocr_tool
        self._translate_tool = translate_tool

    @property
    def name(self) -> str:
        return "translation"

    @property
    def description(self) -> str:
        return "智能翻译 Agent：生成 Prompt → 执行翻译"

    async def run(self, input_data: AgentContext, **kwargs) -> AgentContext:
        ctx = input_data

        # auto_fix 场景：ctx 已有 prompt_profile，跳过 prompt 生成
        is_rerun = ctx.prompt_profile is not None and ctx.translated_md != ""

        pipeline_type = ctx.pipeline_type or "llm"

        if is_rerun:
            logger.info("Auto-fix rerun: reusing existing prompt_profile, skipping prompt generation")
            await ctx.event_bus.publish(ctx.task_id, {
                "agent": "translation",
                "stage": "prompt_generation",
                "progress": 28,
                "detail": {"message": "自动修正: 复用已有 Prompt 配置"},
            })
        else:
            # 生成 Prompt（注入术语表）
            ctx.cancellation_token.check()

            await ctx.event_bus.publish(ctx.task_id, {
                "agent": "translation",
                "stage": "prompt_generation",
                "progress": 26,
                "detail": {"message": "生成翻译 Prompt..."},
            })

            profile = await self._generate_prompt(ctx)
            ctx.prompt_profile = profile
            term_count = len(profile.terminology) if hasattr(profile, 'terminology') else 0
            await ctx.event_bus.publish(ctx.task_id, {
                "agent": "translation",
                "stage": "prompt_generation",
                "progress": 30,
                "detail": {
                    "domain": profile.domain,
                    "message": f"Prompt 已生成 | 领域: {profile.domain} | 术语: {term_count} 个",
                    "term_count": term_count,
                },
            })

        # 执行翻译（带重试）
        ctx.cancellation_token.check()

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "translation",
            "stage": "translating",
            "progress": 32,
            "detail": {"message": f"{'[修正] ' if is_rerun else ''}启动 {'OCR' if pipeline_type == 'ocr' else 'LLM'} 翻译管线..."},
        })

        result = await self._execute_with_retry(pipeline_type, ctx, max_retries=3)
        ctx.translated_md = result.translated_md

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "translation",
            "stage": "complete",
            "progress": 70,
        })

        return ctx

    # ------------------------------------------------------------------
    # Prompt generation
    # ------------------------------------------------------------------

    async def _generate_prompt(self, ctx: AgentContext) -> Any:
        from backend.app.services.prompt_generator import (
            PromptProfile,
            generate_prompt_profile,
            _build_translation_prompt,
        )

        try:
            if self._translate_tool is not None:
                profile = PromptProfile()
            else:
                from backend.app.services.translator import TranslationService
                from core.llm.config import FunctionKey

                translator = await TranslationService.from_manager(FunctionKey.TRANSLATION)
                abstract_text = await self._extract_abstract_text(ctx)
                logger.info("Calling LLM for prompt profile generation (%d chars)...", len(abstract_text))
                profile = await generate_prompt_profile(abstract_text, translator)
                logger.info("Prompt profile generated: domain=%s", profile.domain)
        except Exception as e:
            logger.warning("Prompt generation failed: %s, using default profile", e)
            profile = PromptProfile()

        # Inject glossary terms
        if ctx.glossary:
            for english, chinese in ctx.glossary.items():
                if english not in profile.terminology:
                    profile.terminology[english] = chinese

        profile.translation_prompt = _build_translation_prompt(profile)

        logger.info(
            "Prompt generated: domain=%s, terms=%d (glossary injected: %d)",
            profile.domain, len(profile.terminology), len(ctx.glossary),
        )
        return profile

    async def _extract_abstract_text(self, ctx: AgentContext) -> str:
        try:
            import fitz

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(ctx.file_content)
                tmp_path = tmp.name

            try:
                doc = fitz.open(tmp_path)
                text_parts = []
                for i, page in enumerate(doc):
                    if i >= 2:
                        break
                    text_parts.append(page.get_text())
                doc.close()
                return "\n\n".join(text_parts)
            finally:
                Path(tmp_path).unlink(missing_ok=True)
        except Exception as e:
            logger.warning("Abstract extraction failed: %s", e)
            return ""

    # ------------------------------------------------------------------
    # Translation execution with retry
    # ------------------------------------------------------------------

    async def _execute_with_retry(
        self,
        pipeline_type: str,
        ctx: AgentContext,
        max_retries: int = 3,
    ) -> PipelineResult:
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            ctx.cancellation_token.check()

            try:
                logger.info(
                    "Translation attempt %d/%d using %s pipeline",
                    attempt, max_retries, pipeline_type,
                )

                result = await self._run_pipeline(pipeline_type, ctx)

                progress = min(32 + int(38 * (attempt / max_retries)), 68)
                await ctx.event_bus.publish(ctx.task_id, {
                    "agent": "translation",
                    "stage": "translating",
                    "progress": progress,
                    "detail": {"attempt": attempt, "status": "success"},
                })

                return result

            except asyncio.CancelledError:
                raise

            except Exception as e:
                last_error = e
                logger.warning(
                    "Translation attempt %d/%d failed: %s",
                    attempt, max_retries, e,
                )

                await ctx.event_bus.publish(ctx.task_id, {
                    "agent": "translation",
                    "stage": "translating",
                    "progress": 32 + int(30 * (attempt / max_retries)),
                    "detail": {"attempt": attempt, "status": "retry", "error": str(e)},
                })

                if attempt < max_retries:
                    await asyncio.sleep(0.5 * attempt)

        raise RuntimeError(
            f"Translation failed after {max_retries} attempts: {last_error}"
        )

    async def _run_pipeline(
        self, pipeline_type: str, ctx: AgentContext
    ) -> PipelineResult:
        """Execute translation using the data already parsed by OCRAgent.

        - LLM 管线: 使用 ctx.parsed_pdf（OCRAgent 已缝合）
        - OCR 管线: 使用 ctx.ocr_md（OCRAgent 已预处理）
        """
        system_prompt = (
            ctx.prompt_profile.translation_prompt
            if ctx.prompt_profile
            else None
        )

        if pipeline_type == "ocr":
            from backend.app.services.pipelines.ocr_pipeline import OCRPipeline

            pipeline = OCRPipeline(
                system_prompt=system_prompt,
                token=ctx.cancellation_token,
                event_bus=ctx.event_bus,
                task_id=ctx.task_id,
            )
            # OCRAgent 已经完成 OCR + 预处理，传入已有结果跳过 OCR
            result = await pipeline.execute(
                ctx.file_content, ctx.filename,
                existing_ocr_md=ctx.ocr_md,
                existing_ocr_images=ctx.ocr_images,
            )

        else:  # "llm"
            from backend.app.services.pipelines.llm_pipeline import LLMPipeline

            pipeline = LLMPipeline(
                system_prompt=system_prompt,
                token=ctx.cancellation_token,
                event_bus=ctx.event_bus,
                task_id=ctx.task_id,
            )
            # 如果 OCRAgent 已解析 parsed_pdf，传入跳过重复解析
            result = await pipeline.execute(
                ctx.file_content, ctx.filename,
                existing_parsed_pdf=ctx.parsed_pdf,
            )

        # 将 pipeline 产出的附属数据存回 AgentContext
        if result.images:
            ctx.images.update(result.images)
        if result.ocr_md and not ctx.ocr_md:
            ctx.ocr_md = result.ocr_md
        if result.ocr_images:
            ctx.ocr_images.update(result.ocr_images)
        if result.prompt_profile and not ctx.prompt_profile:
            ctx.prompt_profile = result.prompt_profile

        return result
