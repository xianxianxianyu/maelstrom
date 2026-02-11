"""OrchestratorAgent — 编排 Agent：协调翻译工作流

按"术语准备 → 翻译 → 审校"顺序协调 Agent，质量低于 70 分时自动修正（最多 1 次），
通过 EventBus 推送每个 Agent 的状态变化，保存翻译结果和 QualityReport 到 TranslationStore。

Requirements: 5.1, 5.5, 5.6, 2.5
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent.base import BaseAgent
from agent.context import AgentContext
from agent.registry import agent_registry

logger = logging.getLogger(__name__)

# Quality score threshold for auto-fix
QUALITY_THRESHOLD = 70

# Maximum number of auto-fix retries
MAX_AUTO_FIX_RETRIES = 1


@agent_registry.register
class OrchestratorAgent(BaseAgent):
    """编排 Agent：协调翻译工作流

    Workflow:
        1. 术语准备 (terminology): 调用 TerminologyAgent 提取术语
        2. 翻译 (translation): 调用 TranslationAgent 执行翻译
        3. 审校 (review): 调用 ReviewAgent 生成质量报告
        4. 自动修正 (auto_fix): 质量低于 70 分时重新翻译+审校（最多 1 次）
        5. 保存结果 (save): 保存翻译结果和 QualityReport 到 TranslationStore

    每个阶段通过 AgentContext.event_bus 推送进度事件。

    Attributes:
        _terminology_agent: 术语 Agent 实例（依赖注入）
        _translation_agent: 翻译 Agent 实例（依赖注入）
        _review_agent: 审校 Agent 实例（依赖注入）
        _translation_store: 翻译结果存储实例（依赖注入）
    """

    def __init__(
        self,
        terminology_agent: BaseAgent | None = None,
        ocr_agent: BaseAgent | None = None,
        translation_agent: BaseAgent | None = None,
        review_agent: BaseAgent | None = None,
        index_agent: BaseAgent | None = None,
        translation_store: Any | None = None,
    ) -> None:
        """初始化 OrchestratorAgent

        Args:
            terminology_agent: 可选的 TerminologyAgent 实例（依赖注入，用于测试）
            ocr_agent: 可选的 OCRAgent 实例（依赖注入，用于测试）
            translation_agent: 可选的 TranslationAgent 实例（依赖注入，用于测试）
            review_agent: 可选的 ReviewAgent 实例（依赖注入，用于测试）
            index_agent: 可选的 IndexAgent 实例（依赖注入，用于测试）
            translation_store: 可选的 TranslationStore 实例（依赖注入，用于测试）
        """
        self._terminology_agent = terminology_agent
        self._ocr_agent = ocr_agent
        self._translation_agent = translation_agent
        self._review_agent = review_agent
        self._index_agent = index_agent
        self._translation_store = translation_store

    @property
    def name(self) -> str:
        return "orchestrator"

    @property
    def description(self) -> str:
        return "编排 Agent：协调翻译工作流"

    def _get_terminology_agent(self) -> BaseAgent:
        """获取 TerminologyAgent 实例

        如果未通过依赖注入提供，则从 agent_registry 创建。

        Returns:
            TerminologyAgent 实例
        """
        if self._terminology_agent is not None:
            return self._terminology_agent
        return agent_registry.create("TerminologyAgent")

    def _get_translation_agent(self) -> BaseAgent:
        """获取 TranslationAgent 实例

        如果未通过依赖注入提供，则从 agent_registry 创建。

        Returns:
            TranslationAgent 实例
        """
        if self._translation_agent is not None:
            return self._translation_agent
        return agent_registry.create("TranslationAgent")

    def _get_ocr_agent(self) -> BaseAgent:
        """获取 OCRAgent 实例

        如果未通过依赖注入提供，则从 agent_registry 创建。

        Returns:
            OCRAgent 实例
        """
        if self._ocr_agent is not None:
            return self._ocr_agent
        return agent_registry.create("OCRAgent")

    def _get_review_agent(self) -> BaseAgent:
        """获取 ReviewAgent 实例

        如果未通过依赖注入提供，则从 agent_registry 创建。

        Returns:
            ReviewAgent 实例
        """
        if self._review_agent is not None:
            return self._review_agent
        return agent_registry.create("ReviewAgent")

    def _get_index_agent(self) -> BaseAgent:
        """获取 IndexAgent 实例

        如果未通过依赖注入提供，则从 agent_registry 创建。

        Returns:
            IndexAgent 实例
        """
        if self._index_agent is not None:
            return self._index_agent
        return agent_registry.create("IndexAgent")

    async def _get_translation_store(self) -> Any:
        """获取 TranslationStore 实例

        如果未通过依赖注入提供，则使用全局单例。

        Returns:
            TranslationStore 实例
        """
        if self._translation_store is not None:
            return self._translation_store
        from backend.app.services.translation_store import get_translation_store
        return get_translation_store()

    async def run(self, input_data: AgentContext, **kwargs) -> AgentContext:
        """执行编排 Agent 主逻辑

        按"术语准备 → 翻译 → 审校"顺序协调 Agent，
        质量低于 70 分时自动修正（最多 1 次），
        最后保存翻译结果到 TranslationStore。

        Args:
            input_data: AgentContext 共享上下文

        Returns:
            更新后的 AgentContext

        Raises:
            asyncio.CancelledError: 如果任务被取消
        """
        ctx = input_data

        # Phase 1: 术语准备
        await self._run_terminology_phase(ctx)

        # Phase 2: 文档解析 + 预处理（OCRAgent）
        await self._run_ocr_phase(ctx)

        # Phase 3: 翻译
        await self._run_translation_phase(ctx)

        # Phase 4: 审校
        await self._run_review_phase(ctx)

        # Phase 5: 质量不达标则修正重审（最多 1 次）
        if (
            ctx.quality_report is not None
            and ctx.quality_report.score < QUALITY_THRESHOLD
        ):
            await self._auto_fix_and_review(ctx)

        # Phase 6: 论文索引（提取元数据 → 存入数据库）
        await self._run_index_phase(ctx)

        # Phase 7: 保存结果
        await self._save_results(ctx)

        # 完成
        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "orchestrator",
            "stage": "complete",
            "progress": 100,
        })

        return ctx

    # ------------------------------------------------------------------
    # Phase methods
    # ------------------------------------------------------------------

    async def _run_terminology_phase(self, ctx: AgentContext) -> None:
        """Phase 1: 术语准备

        从文件内容中提取文本，调用 TerminologyAgent 提取术语，
        将结果写入 ctx.glossary。

        Args:
            ctx: AgentContext
        """
        ctx.cancellation_token.check()

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "orchestrator",
            "stage": "terminology",
            "progress": 0,
            "detail": {"message": "开始术语准备..."},
        })

        terminology_agent = self._get_terminology_agent()

        # Extract text from file_content for terminology extraction
        # 只取前 3000 字符（约摘要+引言），避免发送整篇论文给 LLM
        text = self._extract_text_from_content(ctx.file_content)
        if len(text) > 3000:
            text = text[:3000]

        logger.info(
            "Terminology extraction starting: %d chars of text to analyze",
            len(text),
        )

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "orchestrator",
            "stage": "terminology",
            "progress": 3,
            "detail": {"message": f"提取文本 {len(text)} 字符，调用 LLM 分析术语..."},
        })

        try:
            terms_result = await terminology_agent({
                "action": "extract",
                "text": text,
                "domain": "general",
            })

            # Convert glossary entries to simple dict for ctx.glossary
            if isinstance(terms_result, dict):
                glossary_entries = terms_result.get("glossary", [])
                for entry in glossary_entries:
                    if isinstance(entry, dict):
                        english = entry.get("english", "")
                        chinese = entry.get("chinese", "")
                        if english and chinese:
                            ctx.glossary[english] = chinese

            logger.info(
                "Terminology phase complete: %d terms extracted",
                len(ctx.glossary),
            )

        except Exception as e:
            logger.warning("Terminology extraction failed: %s, continuing with empty glossary", e)
            # Non-fatal: continue with whatever glossary we have

        term_count = len(ctx.glossary)
        sample = list(ctx.glossary.items())[:3]
        sample_str = ", ".join(f"{e}→{c}" for e, c in sample) if sample else ""
        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "orchestrator",
            "stage": "terminology",
            "progress": 15,
            "detail": {
                "message": f"术语准备完成: {term_count} 条" + (f" ({sample_str}...)" if sample_str else ""),
                "term_count": term_count,
            },
        })

    async def _run_ocr_phase(self, ctx: AgentContext) -> None:
        """Phase 2: 文档解析 + 预处理

        调用 OCRAgent 执行 PDF 解析/OCR + 跨页缝合 + 表格修复，
        结果写入 ctx.parsed_pdf / ctx.ocr_md。

        Args:
            ctx: AgentContext

        Raises:
            Exception: 解析失败时向上传播
        """
        ctx.cancellation_token.check()

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "orchestrator",
            "stage": "ocr",
            "progress": 16,
            "detail": {"message": "文档解析 + 预处理中..."},
        })

        ocr_agent = self._get_ocr_agent()

        try:
            ctx = await ocr_agent(ctx)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await ctx.event_bus.publish(ctx.task_id, {
                "agent": "orchestrator",
                "stage": "ocr",
                "progress": 16,
                "detail": {"status": "failed", "error": str(e)},
            })
            raise

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "orchestrator",
            "stage": "ocr",
            "progress": 25,
            "detail": {"message": "文档解析 + 预处理完成"},
        })

        logger.info("OCR phase complete: pipeline_type=%s", ctx.pipeline_type)

    async def _run_translation_phase(self, ctx: AgentContext) -> None:
        """Phase 3: 翻译

        调用 TranslationAgent 执行翻译，结果写入 ctx.translated_md。

        Args:
            ctx: AgentContext

        Raises:
            Exception: 翻译失败时向上传播
        """
        ctx.cancellation_token.check()

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "orchestrator",
            "stage": "translation",
            "progress": 26,
            "detail": {"message": "启动翻译管线..."},
        })

        translation_agent = self._get_translation_agent()

        try:
            ctx = await translation_agent(ctx)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await ctx.event_bus.publish(ctx.task_id, {
                "agent": "orchestrator",
                "stage": "translation",
                "progress": 26,
                "detail": {"status": "failed", "error": str(e)},
            })
            raise

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "orchestrator",
            "stage": "translation",
            "progress": 70,
            "detail": {"message": "翻译完成，准备审校..."},
        })

        logger.info("Translation phase complete")

    async def _run_review_phase(self, ctx: AgentContext) -> None:
        """Phase 4: 审校

        调用 ReviewAgent 生成质量报告，结果写入 ctx.quality_report。

        Args:
            ctx: AgentContext

        Raises:
            Exception: 审校失败时向上传播
        """
        ctx.cancellation_token.check()

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "orchestrator",
            "stage": "review",
            "progress": 75,
            "detail": {"message": "质量审校中..."},
        })

        review_agent = self._get_review_agent()

        try:
            ctx = await review_agent(ctx)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await ctx.event_bus.publish(ctx.task_id, {
                "agent": "orchestrator",
                "stage": "review",
                "progress": 75,
                "detail": {"status": "failed", "error": str(e)},
            })
            raise

        score = ctx.quality_report.score if ctx.quality_report else "N/A"
        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "orchestrator",
            "stage": "review",
            "progress": 85,
            "detail": {"message": f"审校完成，质量评分: {score}", "score": score},
        })

        logger.info("Review phase complete: score=%s", score)

    async def _auto_fix_and_review(self, ctx: AgentContext) -> None:
        """Phase 5: 自动修正 + 重新审校

        当质量报告评分低于 QUALITY_THRESHOLD 时，
        重新执行翻译（注入改进建议）和审校（最多 1 次）。

        Args:
            ctx: AgentContext
        """
        ctx.cancellation_token.check()

        logger.info(
            "Quality score %d < %d, starting auto-fix",
            ctx.quality_report.score if ctx.quality_report else 0,
            QUALITY_THRESHOLD,
        )

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "orchestrator",
            "stage": "auto_fix",
            "progress": 87,
            "detail": {"message": f"质量评分 {ctx.quality_report.score if ctx.quality_report else 0} 分 < {QUALITY_THRESHOLD}，自动修正中..."},
        })

        # Re-run translation
        translation_agent = self._get_translation_agent()
        try:
            ctx = await translation_agent(ctx)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Auto-fix translation failed: %s, keeping original", e)
            return

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "orchestrator",
            "stage": "auto_fix",
            "progress": 92,
            "detail": {"message": "修正翻译完成，重新审校中..."},
        })

        # Re-run review
        review_agent = self._get_review_agent()
        try:
            ctx = await review_agent(ctx)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Auto-fix review failed: %s, keeping previous report", e)
            return

        new_score = ctx.quality_report.score if ctx.quality_report else "N/A"
        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "orchestrator",
            "stage": "auto_fix",
            "progress": 95,
            "detail": {"message": f"自动修正完成，新评分: {new_score}", "new_score": new_score},
        })

        logger.info("Auto-fix complete: new score=%s", new_score)

    async def _run_index_phase(self, ctx: AgentContext) -> None:
        """Phase 6: 论文索引

        调用 IndexAgent 提取论文元数据并存入 SQLite 数据库。
        索引失败不阻塞工作流（non-fatal）。

        Args:
            ctx: AgentContext
        """
        ctx.cancellation_token.check()

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "orchestrator",
            "stage": "indexing",
            "progress": 91,
            "detail": {"message": "论文索引中..."},
        })

        index_agent = self._get_index_agent()

        try:
            ctx = await index_agent(ctx)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Index phase failed: %s, continuing without indexing", e)
            await ctx.event_bus.publish(ctx.task_id, {
                "agent": "orchestrator",
                "stage": "indexing",
                "progress": 96,
                "detail": {"status": "failed", "error": str(e), "message": f"索引失败: {e}（不影响翻译结果）"},
            })
            return

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "orchestrator",
            "stage": "indexing",
            "progress": 96,
            "detail": {"message": "论文索引完成"},
        })

        logger.info("Index phase complete: paper_metadata=%s", bool(ctx.paper_metadata))

    async def _save_results(self, ctx: AgentContext) -> None:
        """Phase 7: 保存翻译结果

        将翻译结果和 QualityReport 保存到 TranslationStore。

        Args:
            ctx: AgentContext
        """
        ctx.cancellation_token.check()

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "orchestrator",
            "stage": "saving",
            "progress": 97,
            "detail": {"message": "保存翻译结果..."},
        })

        try:
            store = await self._get_translation_store()

            # Build meta_extra with quality report
            meta_extra: dict[str, Any] = {}
            if ctx.quality_report is not None:
                meta_extra["quality_report"] = ctx.quality_report.to_dict()

            await store.save(
                filename=ctx.filename,
                translated_md=ctx.translated_md,
                images=ctx.images if ctx.images else None,
                ocr_md=ctx.ocr_md,
                ocr_images=ctx.ocr_images if ctx.ocr_images else None,
                meta_extra=meta_extra,
            )

            logger.info("Results saved for task %s", ctx.task_id)

        except Exception as e:
            logger.warning("Failed to save results: %s", e)
            # Non-fatal: the translation is still in ctx

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "orchestrator",
            "stage": "saving",
            "progress": 99,
            "detail": {"message": "结果已保存"},
        })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text_from_content(file_content: bytes) -> str:
        """从文件内容中提取文本

        尝试使用 PyMuPDF (fitz) 提取 PDF 文本。
        如果 fitz 不可用或提取失败，返回空字符串。

        Args:
            file_content: PDF 文件的原始字节内容

        Returns:
            提取的文本字符串
        """
        try:
            import fitz
            import tempfile
            from pathlib import Path

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(file_content)
                tmp_path = tmp.name

            try:
                doc = fitz.open(tmp_path)
                text_parts = []
                for page in doc:
                    text_parts.append(page.get_text())
                doc.close()
                return "\n".join(text_parts)
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        except ImportError:
            logger.debug("PyMuPDF (fitz) not available for text extraction")
            return ""
        except Exception as e:
            logger.debug("Text extraction failed: %s", e)
            return ""
