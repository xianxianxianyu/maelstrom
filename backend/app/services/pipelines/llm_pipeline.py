"""LLM 管线 — PyMuPDF 解析 → 摘要分析 → 逐块翻译 → 组装 Markdown"""
import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

import aiofiles

from app.services.pdf_parser import PDFParser
from app.services.translator import TranslationService
from app.services.markdown_builder import MarkdownBuilder
from app.services.post_processor import PostProcessor
from app.services.text_processing import merge_text_blocks
from app.services.text_processing import postprocess_translated_markdown
from app.services.prompt_generator import (
    generate_prompt_profile, extract_abstract_from_blocks,
)
from core.llm.config import FunctionKey
from .base import BasePipeline, PipelineResult, CancellationToken

logger = logging.getLogger(__name__)


class LLMPipeline(BasePipeline):
    """纯 LLM 管线：PyMuPDF 解析 → 分析摘要生成 prompt → 逐块翻译 → 组装 markdown"""

    async def execute(self, file_content: bytes, filename: str) -> PipelineResult:
        t0 = time.time()
        logger.info("🔤 LLM 管线启动（PyMuPDF 解析）...")

        # 写入临时文件供 PyMuPDF 读取
        temp_path = Path(f"temp/{filename}")
        temp_path.parent.mkdir(exist_ok=True)
        async with aiofiles.open(temp_path, "wb") as f:
            await f.write(file_content)

        try:
            parser = PDFParser()
            translator = await TranslationService.from_manager(FunctionKey.TRANSLATION)
            builder = MarkdownBuilder()

            parsed = await parser.process(temp_path)
            total_pages = len(parsed.pages)
            logger.info(f"   PDF 解析完成: {total_pages} 页")

            # Step 0: 提取摘要 → 生成定制化翻译 prompt
            abstract_text = extract_abstract_from_blocks(parsed.pages)
            profile = await generate_prompt_profile(abstract_text, translator, self.system_prompt)
            final_prompt = profile.translation_prompt
            logger.info(f"📋 翻译 Prompt 已生成 | 领域: {profile.domain} | 术语: {len(profile.terminology)} 个")

            # 并发翻译
            post_processor = PostProcessor()
            sem = asyncio.Semaphore(self.CONCURRENCY)

            async def translate_block(block):
                async with sem:
                    self.token.check()
                    block.text = await translator.translate(block.text, final_prompt)
                    block.text = post_processor.process(block.text)

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

                    elapsed = time.time() - page_start
                    pct = (idx + 1) / total_pages * 100
                    logger.info(
                        f"   翻译进度: [{idx + 1}/{total_pages}] {pct:.0f}% "
                        f"| {len(text_blocks)}→{len(merged_blocks)} 块 | {elapsed:.1f}s"
                    )

            md, images = await builder.process(parsed)
            # 后处理 — 引用上标、图注格式化
            md = postprocess_translated_markdown(md)
            logger.info(f"✅ LLM 管线完成 | {len(md)} 字符 | 耗时 {time.time() - t0:.1f}s")

            return PipelineResult(
                translated_md=md,
                images=images,
                prompt_profile=profile,
            )
        finally:
            # 清理临时文件
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
