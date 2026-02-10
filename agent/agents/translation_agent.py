"""TranslationAgent — 智能翻译 Agent

分析文档特征 → 选择最优管线 → 注入术语表 → 执行翻译（带重试）。
每个阶段通过 AgentContext.event_bus 推送进度事件。

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 1.8
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from agent.base import BaseAgent
from agent.context import AgentContext
from agent.registry import agent_registry
from agent.tools.base import ToolResult
from backend.app.services.pipelines.base import PipelineResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

@dataclass
class DocumentAnalysis:
    """文档分析结果"""
    doc_type: str = "scanned"  # "scanned" or "native"
    language_distribution: dict[str, float] = field(default_factory=dict)
    formula_density: float = 0.0
    table_count: int = 0

    def to_dict(self) -> dict:
        return {
            "doc_type": self.doc_type,
            "language_distribution": dict(self.language_distribution),
            "formula_density": self.formula_density,
            "table_count": self.table_count,
        }


def _count_formulas(text: str) -> tuple[int, int]:
    """Count LaTeX formulas in text.

    Returns:
        (formula_count, total_chars) for computing density.
    """
    # Match display math $$...$$ and inline math $...$
    display_math = re.findall(r"\$\$.*?\$\$", text, re.DOTALL)
    inline_math = re.findall(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", text)
    formula_count = len(display_math) + len(inline_math)
    total_chars = max(len(text), 1)
    return formula_count, total_chars


def _count_tables(text: str) -> int:
    """Count markdown tables in text (lines matching | col | col | pattern)."""
    # A markdown table has at least a header row and a separator row
    lines = text.split("\n")
    table_count = 0
    i = 0
    while i < len(lines) - 1:
        line = lines[i].strip()
        next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
        # Check for table header + separator pattern
        if (
            line.startswith("|")
            and "|" in line[1:]
            and re.match(r"^\|[\s\-:|]+\|", next_line)
        ):
            table_count += 1
            # Skip past this table
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                i += 1
            continue
        i += 1
    return table_count


def _detect_language_distribution(text: str) -> dict[str, float]:
    """Estimate language distribution in text.

    Returns dict with approximate ratios for 'en', 'zh', 'other'.
    """
    if not text:
        return {"en": 0.0, "zh": 0.0, "other": 0.0}

    total = len(text)
    zh_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    en_chars = len(re.findall(r"[a-zA-Z]", text))
    other = total - zh_chars - en_chars

    return {
        "en": round(en_chars / max(total, 1), 3),
        "zh": round(zh_chars / max(total, 1), 3),
        "other": round(max(other, 0) / max(total, 1), 3),
    }


# ---------------------------------------------------------------------------
# TranslationAgent
# ---------------------------------------------------------------------------

@agent_registry.register
class TranslationAgent(BaseAgent):
    """智能翻译 Agent：分析文档 → 选择策略 → 执行翻译

    Workflow:
        1. _analyze_document: 分析 PDF 特征（扫描件/原生、公式密度、表格数量）
        2. _select_pipeline: 根据分析结果选择 OCR 或 LLM 管线
        3. _generate_prompt: 注入术语表生成翻译 prompt
        4. _execute_with_retry: 带重试的翻译执行（最多 3 次）

    每个阶段通过 AgentContext.event_bus 推送进度事件。
    """

    # Minimum extractable text length to consider a PDF as "native"
    NATIVE_TEXT_THRESHOLD = 200

    def __init__(
        self,
        ocr_tool: Any | None = None,
        translate_tool: Any | None = None,
    ) -> None:
        """初始化 TranslationAgent

        Args:
            ocr_tool: 可选的 OCRTool 实例（依赖注入，用于测试）
            translate_tool: 可选的 TranslateTool 实例（依赖注入，用于测试）
        """
        self._ocr_tool = ocr_tool
        self._translate_tool = translate_tool

    @property
    def name(self) -> str:
        return "translation"

    @property
    def description(self) -> str:
        return "智能翻译 Agent：分析文档 → 选择策略 → 执行翻译"

    async def run(self, input_data: AgentContext, **kwargs) -> AgentContext:
        """执行翻译 Agent 主逻辑

        如果 ctx 已有 prompt_profile（auto_fix 场景），跳过文档分析和 prompt 生成，
        直接复用已有配置重新翻译。

        Args:
            input_data: AgentContext 共享上下文

        Returns:
            更新后的 AgentContext（translated_md 已填充）
        """
        ctx = input_data

        # auto_fix 场景：ctx 已有 prompt_profile，跳过分析和 prompt 生成
        is_rerun = ctx.prompt_profile is not None and ctx.translated_md != ""

        if is_rerun:
            logger.info("Auto-fix rerun: reusing existing prompt_profile, skipping analysis")
            await ctx.event_bus.publish(ctx.task_id, {
                "agent": "translation",
                "stage": "analysis",
                "progress": 10,
                "detail": {"message": "自动修正: 复用已有配置，跳过文档分析"},
            })
            # 仍然需要确定管线类型
            doc_analysis = DocumentAnalysis(doc_type="native" if not ctx.enable_ocr else "scanned")
            pipeline_type = self._select_pipeline(doc_analysis, ctx)
        else:
            # 1. 分析文档特征
            doc_analysis = await self._analyze_document(ctx)
            await ctx.event_bus.publish(ctx.task_id, {
                "agent": "translation",
                "stage": "analysis",
                "progress": 10,
                "detail": {
                    **doc_analysis.to_dict(),
                    "message": f"文档分析: {'原生PDF' if doc_analysis.doc_type == 'native' else '扫描件'}, 公式密度 {doc_analysis.formula_density:.4f}, 表格 {doc_analysis.table_count} 个",
                },
            })

            # Check cancellation
            ctx.cancellation_token.check()

            # 2. 选择管线
            pipeline_type = self._select_pipeline(doc_analysis, ctx)
            await ctx.event_bus.publish(ctx.task_id, {
                "agent": "translation",
                "stage": "pipeline_selection",
                "progress": 15,
                "detail": {
                    "pipeline": pipeline_type,
                    "message": f"选择管线: {'OCR + 翻译' if pipeline_type == 'ocr' else 'LLM 直接翻译'}",
                },
            })

            # Check cancellation
            ctx.cancellation_token.check()

            # 3. 注入术语表到 prompt
            profile = await self._generate_prompt(ctx)
            ctx.prompt_profile = profile
            term_count = len(profile.terminology) if hasattr(profile, 'terminology') else 0
            await ctx.event_bus.publish(ctx.task_id, {
                "agent": "translation",
                "stage": "prompt_generation",
                "progress": 20,
                "detail": {
                    "domain": profile.domain,
                    "message": f"Prompt 已生成 | 领域: {profile.domain} | 术语: {term_count} 个",
                    "term_count": term_count,
                },
            })

        # Check cancellation
        ctx.cancellation_token.check()

        # 4. 执行翻译（带重试）
        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "translation",
            "stage": "translating",
            "progress": 30,
            "detail": {"message": f"{'[修正] ' if is_rerun else ''}启动 {'OCR' if pipeline_type == 'ocr' else 'LLM'} 翻译管线..."},
        })

        result = await self._execute_with_retry(pipeline_type, ctx, max_retries=3)
        ctx.translated_md = result.translated_md

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "translation",
            "stage": "complete",
            "progress": 95,
        })

        return ctx

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    async def _analyze_document(self, ctx: AgentContext) -> DocumentAnalysis:
        """分析 PDF 文档特征

        使用 PyMuPDF (fitz) 尝试提取文本：
        - 如果提取到足够文本 → "native"
        - 否则 → "scanned"

        同时统计公式密度和表格数量。

        Args:
            ctx: AgentContext（使用 file_content）

        Returns:
            DocumentAnalysis 包含 doc_type, language_distribution,
            formula_density, table_count
        """
        analysis = DocumentAnalysis()
        extracted_text = ""

        try:
            import fitz  # PyMuPDF

            # Write to temp file for fitz to open
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(ctx.file_content)
                tmp_path = tmp.name

            try:
                doc = fitz.open(tmp_path)
                text_parts = []
                for page in doc:
                    text_parts.append(page.get_text())
                doc.close()
                extracted_text = "\n".join(text_parts)
            finally:
                Path(tmp_path).unlink(missing_ok=True)

            if len(extracted_text.strip()) >= self.NATIVE_TEXT_THRESHOLD:
                analysis.doc_type = "native"
            else:
                analysis.doc_type = "scanned"

        except ImportError:
            logger.warning("PyMuPDF (fitz) not available, defaulting to 'scanned'")
            analysis.doc_type = "scanned"
        except Exception as e:
            logger.warning("Document analysis failed: %s, defaulting to 'scanned'", e)
            analysis.doc_type = "scanned"

        # Compute formula density and table count from extracted text
        if extracted_text:
            formula_count, total_chars = _count_formulas(extracted_text)
            analysis.formula_density = round(formula_count / max(total_chars, 1), 6)
            analysis.table_count = _count_tables(extracted_text)
            analysis.language_distribution = _detect_language_distribution(
                extracted_text
            )
        else:
            analysis.language_distribution = {"en": 0.0, "zh": 0.0, "other": 0.0}

        logger.info(
            "Document analysis: type=%s, formulas=%.4f, tables=%d",
            analysis.doc_type,
            analysis.formula_density,
            analysis.table_count,
        )
        return analysis

    def _select_pipeline(
        self, doc_analysis: DocumentAnalysis, ctx: AgentContext
    ) -> str:
        """根据文档分析结果和用户选择选择翻译管线

        优先级：
        1. 用户明确开启 OCR (ctx.enable_ocr=True) + OCR 可用 → "ocr"
        2. 用户明确开启 OCR + OCR 不可用 → "llm" (fallback + 警告)
        3. scanned + OCR 可用 → "ocr"
        4. native → "llm"

        Args:
            doc_analysis: 文档分析结果
            ctx: AgentContext

        Returns:
            "ocr" 或 "llm"
        """
        # 用户明确选择 OCR 时，优先尊重用户选择
        if ctx.enable_ocr:
            if self._is_ocr_available():
                logger.info("Pipeline selection: user requested OCR → ocr")
                return "ocr"
            else:
                logger.warning(
                    "Pipeline selection: user requested OCR but unavailable → llm (fallback)"
                )
                return "llm"

        if doc_analysis.doc_type == "native":
            logger.info("Pipeline selection: native PDF → llm")
            return "llm"

        # scanned: check OCR availability
        if self._is_ocr_available():
            logger.info("Pipeline selection: scanned PDF + OCR available → ocr")
            return "ocr"
        else:
            logger.info(
                "Pipeline selection: scanned PDF but OCR unavailable → llm (fallback)"
            )
            return "llm"

    def _is_ocr_available(self) -> bool:
        """Check if OCR binding is available.

        Returns:
            True if OCR can be used, False otherwise.
        """
        try:
            from backend.app.services.ocr_service import OCRService
            return True
        except ImportError:
            return False

    async def _generate_prompt(self, ctx: AgentContext) -> Any:
        """生成翻译 prompt，注入术语表

        使用 generate_prompt_profile() 生成基础 profile，
        然后将 ctx.glossary 中的术语注入到 profile.terminology 中。

        Args:
            ctx: AgentContext（使用 glossary, file_content）

        Returns:
            PromptProfile 实例
        """
        from backend.app.services.prompt_generator import (
            PromptProfile,
            generate_prompt_profile,
            _build_translation_prompt,
        )

        # Try to extract abstract text for prompt generation
        abstract_text = ""
        try:
            # If we have a translate tool or can create a translation service,
            # use generate_prompt_profile for full analysis
            if self._translate_tool is not None:
                # For testing: create a minimal profile
                profile = PromptProfile()
            else:
                from backend.app.services.translator import TranslationService
                from core.llm.config import FunctionKey

                translator = await TranslationService.from_manager(
                    FunctionKey.TRANSLATION
                )
                # Try to get abstract from file content
                abstract_text = await self._extract_abstract_text(ctx)
                logger.info("Calling LLM for prompt profile generation (%d chars)...", len(abstract_text))
                profile = await generate_prompt_profile(abstract_text, translator)
                logger.info("Prompt profile generated: domain=%s", profile.domain)
        except Exception as e:
            logger.warning("Prompt generation failed: %s, using default profile", e)
            profile = PromptProfile()

        # Inject glossary terms into the profile
        if ctx.glossary:
            for english, chinese in ctx.glossary.items():
                if english not in profile.terminology:
                    profile.terminology[english] = chinese

        # Rebuild the translation prompt with injected terms
        profile.translation_prompt = _build_translation_prompt(profile)

        logger.info(
            "Prompt generated: domain=%s, terms=%d (glossary injected: %d)",
            profile.domain,
            len(profile.terminology),
            len(ctx.glossary),
        )
        return profile

    async def _extract_abstract_text(self, ctx: AgentContext) -> str:
        """Try to extract abstract text from file content for prompt generation.

        Args:
            ctx: AgentContext

        Returns:
            Abstract text string (may be empty if extraction fails)
        """
        try:
            import fitz

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(ctx.file_content)
                tmp_path = tmp.name

            try:
                doc = fitz.open(tmp_path)
                text_parts = []
                for i, page in enumerate(doc):
                    if i >= 2:  # Only first 2 pages for abstract
                        break
                    text_parts.append(page.get_text())
                doc.close()
                return "\n\n".join(text_parts)
            finally:
                Path(tmp_path).unlink(missing_ok=True)
        except Exception as e:
            logger.warning("Abstract extraction failed: %s", e)
            return ""

    async def _execute_with_retry(
        self,
        pipeline_type: str,
        ctx: AgentContext,
        max_retries: int = 3,
    ) -> PipelineResult:
        """执行翻译管线，失败时重试

        Args:
            pipeline_type: "ocr" 或 "llm"
            ctx: AgentContext
            max_retries: 最大重试次数（默认 3）

        Returns:
            PipelineResult

        Raises:
            asyncio.CancelledError: 如果任务被取消
            RuntimeError: 如果所有重试都失败
        """
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            # Check cancellation before each attempt
            ctx.cancellation_token.check()

            try:
                logger.info(
                    "Translation attempt %d/%d using %s pipeline",
                    attempt,
                    max_retries,
                    pipeline_type,
                )

                result = await self._run_pipeline(pipeline_type, ctx)

                # Publish progress on success
                progress = min(30 + int(60 * (attempt / max_retries)), 90)
                await ctx.event_bus.publish(ctx.task_id, {
                    "agent": "translation",
                    "stage": "translating",
                    "progress": progress,
                    "detail": {
                        "attempt": attempt,
                        "status": "success",
                    },
                })

                return result

            except asyncio.CancelledError:
                # Re-raise cancellation — don't retry
                raise

            except Exception as e:
                last_error = e
                logger.warning(
                    "Translation attempt %d/%d failed: %s",
                    attempt,
                    max_retries,
                    e,
                )

                # Publish retry event
                await ctx.event_bus.publish(ctx.task_id, {
                    "agent": "translation",
                    "stage": "translating",
                    "progress": 30 + int(50 * (attempt / max_retries)),
                    "detail": {
                        "attempt": attempt,
                        "status": "retry",
                        "error": str(e),
                    },
                })

                if attempt < max_retries:
                    # Brief delay before retry
                    await asyncio.sleep(0.5 * attempt)

        # All retries exhausted
        raise RuntimeError(
            f"Translation failed after {max_retries} attempts: {last_error}"
        )

    async def _run_pipeline(
        self, pipeline_type: str, ctx: AgentContext
    ) -> PipelineResult:
        """Execute the selected pipeline.

        Delegates to existing OCRPipeline or LLMPipeline.
        将 pipeline 返回的 images/ocr_md/ocr_images 存回 AgentContext。

        在 auto_fix 场景下，如果 ctx 已有 ocr_md，传给 OCRPipeline 跳过重复 OCR。

        Args:
            pipeline_type: "ocr" or "llm"
            ctx: AgentContext

        Returns:
            PipelineResult
        """
        # Agent 已经生成了完整的 translation_prompt，传给 pipeline 作为 system_prompt
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
            # auto_fix 场景：复用已有 OCR 结果
            if ctx.ocr_md:
                result = await pipeline.execute(
                    ctx.file_content, ctx.filename,
                    existing_ocr_md=ctx.ocr_md,
                    existing_ocr_images=ctx.ocr_images,
                )
            else:
                result = await pipeline.execute(ctx.file_content, ctx.filename)

        else:  # "llm"
            from backend.app.services.pipelines.llm_pipeline import LLMPipeline

            pipeline = LLMPipeline(
                system_prompt=system_prompt,
                token=ctx.cancellation_token,
                event_bus=ctx.event_bus,
                task_id=ctx.task_id,
            )
            result = await pipeline.execute(ctx.file_content, ctx.filename)

        # 将 pipeline 产出的附属数据存回 AgentContext
        if result.images:
            ctx.images.update(result.images)
        if result.ocr_md:
            ctx.ocr_md = result.ocr_md
        if result.ocr_images:
            ctx.ocr_images.update(result.ocr_images)
        # 如果 pipeline 也生成了 prompt_profile，合并术语（agent 的优先）
        if result.prompt_profile and not ctx.prompt_profile:
            ctx.prompt_profile = result.prompt_profile

        return result
