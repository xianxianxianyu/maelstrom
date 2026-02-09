"""OCR + 翻译管线 — OCR 识别 → 预处理 → 分段 → 翻译文本段 → 重组 Markdown"""
import asyncio
import logging
import time
from typing import Optional

from app.services.translator import TranslationService
from app.services.ocr_service import OCRService
from app.services.post_processor import PostProcessor
from app.services.text_processing import (
    split_md_segments,
    preprocess_ocr_markdown,
    protect_inline_latex,
    restore_inline_latex,
    postprocess_translated_markdown,
)
from app.services.prompt_generator import (
    generate_prompt_profile, extract_abstract_from_markdown,
)
from core.llm.config import FunctionKey
from .base import BasePipeline, PipelineResult, CancellationToken

logger = logging.getLogger(__name__)


class OCRPipeline(BasePipeline):
    """OCR + 翻译管线：OCR → 预处理 → 分析摘要 → 分段翻译 → 重组"""

    async def execute(self, file_content: bytes, filename: str) -> PipelineResult:
        t0 = time.time()
        logger.info("🔍 OCR + 翻译管线启动...")

        # Step 1: OCR 识别
        ocr_service = await OCRService.from_manager()
        ocr_md, ocr_images = await ocr_service.recognize(file_content, file_type=0)
        logger.info(f"   OCR 完成 | {len(ocr_md)} 字符 | 耗时 {time.time() - t0:.1f}s")

        self.token.check()

        # Step 1.5: 预处理 — HTML table → MD table, 图注标准化
        processed_md = preprocess_ocr_markdown(ocr_md)
        logger.info(f"   预处理完成 | {len(ocr_md)} → {len(processed_md)} 字符")

        # Step 2: 提取摘要 → 生成定制化翻译 prompt
        translator = await TranslationService.from_manager(FunctionKey.TRANSLATION)
        abstract_text = extract_abstract_from_markdown(processed_md)
        profile = await generate_prompt_profile(abstract_text, translator, self.system_prompt)
        final_prompt = profile.translation_prompt
        logger.info(f"📋 翻译 Prompt 已生成 | 领域: {profile.domain} | 术语: {len(profile.terminology)} 个")

        self.token.check()

        # Step 3: 分段
        segments = split_md_segments(processed_md)
        text_segments = [s for s in segments if s["type"] == "text"]
        logger.info(f"   分段完成 | 总 {len(segments)} 段 | 文本 {len(text_segments)} 段待翻译")

        # Step 4: 并发翻译文本段（带 LaTeX 保护）
        post_processor = PostProcessor()
        sem = asyncio.Semaphore(self.CONCURRENCY)
        translated_count = 0

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
                if translated_count % 5 == 0 or translated_count == len(text_segments):
                    logger.info(
                        f"   翻译进度: [{translated_count}/{len(text_segments)}] "
                        f"{translated_count / len(text_segments) * 100:.0f}%"
                    )

        await asyncio.gather(*(translate_segment(s) for s in text_segments))

        # Step 5: 重组
        parts = [seg["content"] for seg in segments]
        result_md = "\n\n".join(parts)

        # Step 6: 后处理 — 引用上标、图注格式化
        result_md = postprocess_translated_markdown(result_md)

        logger.info(f"✅ OCR + 翻译管线完成 | {len(result_md)} 字符 | 耗时 {time.time() - t0:.1f}s")

        return PipelineResult(
            translated_md=result_md,
            ocr_md=ocr_md,
            ocr_images=ocr_images,
            prompt_profile=profile,
        )
