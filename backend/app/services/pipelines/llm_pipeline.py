"""LLM 管线 — PyMuPDF 解析 → 摘要分析 → 逐块翻译 → 组装 Markdown"""
import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

import aiofiles

from backend.app.services.pdf_parser import PDFParser
from backend.app.services.translator import TranslationService
from backend.app.services.markdown_builder import MarkdownBuilder
from backend.app.services.post_processor import PostProcessor
from backend.app.services.text_processing import merge_text_blocks
from backend.app.services.text_processing import postprocess_translated_markdown
from backend.app.services.prompt_generator import (
    PromptProfile, generate_prompt_profile, extract_abstract_from_blocks,
)
from core.llm.config import FunctionKey
from .base import BasePipeline, PipelineResult, CancellationToken

logger = logging.getLogger(__name__)


class LLMPipeline(BasePipeline):
    """纯 LLM 管线：PyMuPDF 解析 → 分析摘要生成 prompt → 逐块翻译 → 组装 markdown"""

    async def execute(self, file_content: bytes, filename: str, existing_parsed_pdf=None) -> PipelineResult:
        t0 = time.time()
        logger.info("🔤 LLM 管线启动（PyMuPDF 解析）...")

        temp_path = None

        try:
            translator = await TranslationService.from_manager(FunctionKey.TRANSLATION)
            builder = MarkdownBuilder()

            # 如果 OCRAgent 已解析，直接复用
            if existing_parsed_pdf is not None:
                parsed = existing_parsed_pdf
                total_pages = len(parsed.pages)
                logger.info(f"   复用已有 ParsedPDF: {total_pages} 页（跳过解析）")
                await self._emit("pdf_parsed", 35, {
                    "message": f"复用已有解析结果: {total_pages} 页",
                    "total_pages": total_pages,
                })
            else:
                await self._emit("pdf_parsing", 30, {"message": "PyMuPDF 解析 PDF 中..."})
                temp_path = Path(f"temp/{filename}")
                temp_path.parent.mkdir(exist_ok=True)
                async with aiofiles.open(temp_path, "wb") as f:
                    await f.write(file_content)

                parser = PDFParser()
                parsed = await parser.process(temp_path)
                total_pages = len(parsed.pages)
                logger.info(f"   PDF 解析完成: {total_pages} 页")
                await self._emit("pdf_parsed", 35, {
                    "message": f"PDF 解析完成: {total_pages} 页",
                    "total_pages": total_pages,
                })

            # Step 0: 提取摘要 → 生成定制化翻译 prompt
            if self.system_prompt:
                final_prompt = self.system_prompt
                profile = PromptProfile(translation_prompt=final_prompt)
                logger.info("📋 使用上层传入的翻译 Prompt（跳过重复生成）")
                await self._emit("prompt_ready", 40, {
                    "message": "使用 Agent 生成的翻译 Prompt",
                })
            else:
                await self._emit("prompt_generating", 37, {
                    "message": "分析论文领域和术语...",
                })
                abstract_text = extract_abstract_from_blocks(parsed.pages)
                profile = await generate_prompt_profile(abstract_text, translator, self.system_prompt)
                final_prompt = profile.translation_prompt
                logger.info(f"📋 翻译 Prompt 已生成 | 领域: {profile.domain} | 术语: {len(profile.terminology)} 个")
                await self._emit("prompt_ready", 40, {
                    "message": f"Prompt 已生成 | 领域: {profile.domain} | 术语: {len(profile.terminology)} 个",
                    "domain": profile.domain,
                    "term_count": len(profile.terminology),
                })

            # 并发翻译
            post_processor = PostProcessor()
            sem = asyncio.Semaphore(self.CONCURRENCY)
            translated_pages = 0

            async def translate_block(block):
                async with sem:
                    self.token.check()
                    block.text = await translator.translate(block.text, final_prompt)
                    block.text = post_processor.process(block.text)

            await self._emit("translating", 45, {
                "message": f"开始翻译 {total_pages} 页...",
                "current": 0,
                "total": total_pages,
            })

            for idx, page in enumerate(parsed.pages):
                self.token.check()

                page_start = time.time()
                text_blocks = [b for b in page.blocks if b.type == "text" and b.text.strip()]
                merged_blocks = merge_text_blocks(text_blocks)

                if merged_blocks:
                    await asyncio.gather(*(translate_block(b) for b in merged_blocks))
                    non_text = [b for b in page.blocks if b.type != "text" or not b.text.strip()]
                    page.blocks = non_text + merged_blocks
                    page.blocks.sort(key=lambda b: b.y_pos)

                translated_pages += 1
                pct = translated_pages / total_pages
                progress = 45 + int(pct * 40)
                elapsed = time.time() - page_start
                logger.info(
                    f"   翻译进度: [{translated_pages}/{total_pages}] {pct * 100:.0f}% "
                    f"| {len(text_blocks)}→{len(merged_blocks)} 块 | {elapsed:.1f}s"
                )
                if translated_pages % 2 == 0 or translated_pages == total_pages:
                    await self._emit("translating", progress, {
                        "message": f"翻译中: {translated_pages}/{total_pages} 页 ({pct * 100:.0f}%)",
                        "current": translated_pages,
                        "total": total_pages,
                    })

            md, images = await builder.process(parsed)
            # 后处理 — 引用上标、图注格式化
            md = postprocess_translated_markdown(md)
            total_time = time.time() - t0
            logger.info(f"✅ LLM 管线完成 | {len(md)} 字符 | 耗时 {total_time:.1f}s")
            await self._emit("pipeline_done", 92, {
                "message": f"翻译管线完成: {len(md)} 字符, 耗时 {total_time:.1f}s",
            })

            return PipelineResult(
                translated_md=md,
                images=images,
                prompt_profile=profile,
            )
        finally:
            # 清理临时文件
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
