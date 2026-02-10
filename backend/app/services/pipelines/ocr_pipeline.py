"""OCR + 翻译管线 — OCR 识别 → 预处理 → 分段 → 翻译文本段 → 重组 Markdown"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from backend.app.services.translator import TranslationService
from backend.app.services.ocr_service import OCRService
from backend.app.services.post_processor import PostProcessor
from backend.app.services.text_processing import (
    split_md_segments,
    preprocess_ocr_markdown,
    protect_inline_latex,
    restore_inline_latex,
    postprocess_translated_markdown,
)
from backend.app.services.prompt_generator import (
    PromptProfile, generate_prompt_profile, extract_abstract_from_markdown,
)
from core.llm.config import FunctionKey
from .base import BasePipeline, PipelineResult, CancellationToken

logger = logging.getLogger(__name__)


class OCRPipeline(BasePipeline):
    """OCR + 翻译管线：OCR → 预处理 → 分析摘要 → 分段翻译 → 重组"""

    async def execute(
        self,
        file_content: bytes,
        filename: str,
        existing_ocr_md: str | None = None,
        existing_ocr_images: dict[str, bytes] | None = None,
    ) -> PipelineResult:
        t0 = time.time()
        logger.info("🔍 OCR + 翻译管线启动...")

        # Step 1: OCR 识别（如果已有 OCR 结果则跳过）
        if existing_ocr_md:
            ocr_md = existing_ocr_md
            ocr_images = existing_ocr_images or {}
            logger.info(f"   复用已有 OCR 结果 | {len(ocr_md)} 字符（跳过 OCR）")
            await self._emit("ocr_done", 40, {
                "message": f"复用已有 OCR 结果: {len(ocr_md)} 字符",
            })
        else:
            await self._emit("ocr_start", 30, {"message": "OCR 识别中..."})
            ocr_service = await OCRService.from_manager()
            ocr_md, ocr_images = await ocr_service.recognize(file_content, file_type=0)
            elapsed_ocr = time.time() - t0
            logger.info(f"   OCR 完成 | {len(ocr_md)} 字符 | 耗时 {elapsed_ocr:.1f}s")
            await self._emit("ocr_done", 40, {
                "message": f"OCR 完成: {len(ocr_md)} 字符, 耗时 {elapsed_ocr:.1f}s",
            })

        self.token.check()

        # Step 1.5: 预处理 — HTML table → MD table, 图注标准化
        processed_md = preprocess_ocr_markdown(ocr_md)
        logger.info(f"   预处理完成 | {len(ocr_md)} → {len(processed_md)} 字符")
        await self._emit("preprocess", 42, {
            "message": f"预处理完成: {len(ocr_md)} → {len(processed_md)} 字符",
        })

        # Step 2: 提取摘要 → 生成定制化翻译 prompt
        translator = await TranslationService.from_manager(FunctionKey.TRANSLATION)
        if self.system_prompt:
            final_prompt = self.system_prompt
            profile = PromptProfile(translation_prompt=final_prompt)
            logger.info("📋 使用上层传入的翻译 Prompt（跳过重复生成）")
            await self._emit("prompt_ready", 45, {
                "message": "使用 Agent 生成的翻译 Prompt",
            })
        else:
            await self._emit("prompt_generating", 43, {
                "message": "分析论文领域和术语...",
            })
            abstract_text = extract_abstract_from_markdown(processed_md)
            profile = await generate_prompt_profile(abstract_text, translator, self.system_prompt)
            final_prompt = profile.translation_prompt
            logger.info(f"📋 翻译 Prompt 已生成 | 领域: {profile.domain} | 术语: {len(profile.terminology)} 个")
            await self._emit("prompt_ready", 45, {
                "message": f"Prompt 已生成 | 领域: {profile.domain} | 术语: {len(profile.terminology)} 个",
                "domain": profile.domain,
                "term_count": len(profile.terminology),
            })

        self.token.check()

        # Step 3: 分段
        segments = split_md_segments(processed_md)
        text_segments = [s for s in segments if s["type"] == "text"]
        logger.info(f"   分段完成 | 总 {len(segments)} 段 | 文本 {len(text_segments)} 段待翻译")
        await self._emit("segmented", 47, {
            "message": f"分段完成: {len(text_segments)} 段文本待翻译",
            "total_segments": len(segments),
            "text_segments": len(text_segments),
        })

        # Step 4: 并发翻译文本段（带 LaTeX 保护）
        post_processor = PostProcessor()
        sem = asyncio.Semaphore(self.CONCURRENCY)
        translated_count = 0
        total_text = len(text_segments)

        async def translate_segment(seg: dict):
            nonlocal translated_count
            async with sem:
                self.token.check()
                original = seg["content"]

                # 保护行内 LaTeX 公式
                protected, latex_map = protect_inline_latex(original)

                translated = await translator.translate(protected, final_prompt)
                translated = post_processor.process(translated)

                # 还原 LaTeX 公式
                if latex_map:
                    translated = restore_inline_latex(translated, latex_map)

                seg["content"] = translated
                translated_count += 1
                pct = translated_count / max(total_text, 1)
                # 翻译进度映射到 50-90 区间
                progress = 50 + int(pct * 40)
                if translated_count % 3 == 0 or translated_count == total_text:
                    logger.info(
                        f"   翻译进度: [{translated_count}/{total_text}] "
                        f"{pct * 100:.0f}%"
                    )
                    await self._emit("translating", progress, {
                        "message": f"翻译中: {translated_count}/{total_text} 段 ({pct * 100:.0f}%)",
                        "current": translated_count,
                        "total": total_text,
                    })

        await self._emit("translating", 50, {
            "message": f"开始翻译 {total_text} 段文本...",
            "current": 0,
            "total": total_text,
        })
        await asyncio.gather(*(translate_segment(s) for s in text_segments))

        # Step 5: 重组
        parts = [seg["content"] for seg in segments]
        result_md = "\n\n".join(parts)

        # Step 6: 后处理 — 引用上标、图注格式化
        result_md = postprocess_translated_markdown(result_md)
        total_time = time.time() - t0
        logger.info(f"✅ OCR + 翻译管线完成 | {len(result_md)} 字符 | 耗时 {total_time:.1f}s")
        await self._emit("pipeline_done", 92, {
            "message": f"翻译管线完成: {len(result_md)} 字符, 耗时 {total_time:.1f}s",
        })

        return PipelineResult(
            translated_md=result_md,
            ocr_md=ocr_md,
            ocr_images=ocr_images,
            prompt_profile=profile,
        )
