import asyncio
import logging
import re
import time
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from app.services.pdf_parser import PDFParser, ContentBlock
from app.services.translator import TranslationService
from app.services.markdown_builder import MarkdownBuilder
from app.services.post_processor import PostProcessor
from app.services.ocr_service import OCRService
from app.services.task_manager import get_task_manager
from app.services.translation_store import get_translation_store
from app.services.prompt_generator import (
    generate_prompt_profile, extract_abstract_from_blocks,
    extract_abstract_from_markdown, PromptProfile,
)
from core.providers.base import ProviderConfig
from core.llm.manager import get_llm_manager
from core.ocr.manager import get_ocr_manager
from app.core.key_store import get_api_key
from app.models.schemas import TranslationResponse
import aiofiles
from pathlib import Path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pdf", tags=["pdf"])


# ---------------------------------------------------------------------------
#  Markdown 分段工具 — 将 OCR 输出的 markdown 按段落切分，保留非文本元素
# ---------------------------------------------------------------------------

def _split_md_segments(md_text: str) -> list[dict]:
    """
    将 OCR 输出的 markdown 切分为有序段落列表。
    每个段落是 dict: {"type": "text"|"non_text", "content": str}
    - non_text: 图片 (![...)、表格 (| ... |)、公式块 ($$...$$)、HTML 注释
    - text: 需要翻译的英文段落
    相邻的短文本段落会合并（<1500 字符），给 LLM 更好的上下文。
    """
    lines = md_text.split("\n")
    segments: list[dict] = []
    buf: list[str] = []
    buf_type = "text"

    def flush():
        nonlocal buf, buf_type
        if not buf:
            return
        content = "\n".join(buf).strip()
        if content:
            segments.append({"type": buf_type, "content": content})
        buf = []
        buf_type = "text"

    in_table = False
    in_math_block = False

    for line in lines:
        stripped = line.strip()

        # 数学公式块 $$...$$
        if stripped.startswith("$$") and not in_math_block:
            flush()
            buf_type = "non_text"
            buf.append(line)
            if stripped.endswith("$$") and len(stripped) > 2:
                flush()
            else:
                in_math_block = True
            continue
        if in_math_block:
            buf.append(line)
            if stripped.endswith("$$"):
                in_math_block = False
                flush()
            continue

        # 图片行
        if re.match(r"^\s*!\[", stripped):
            flush()
            segments.append({"type": "non_text", "content": line})
            continue

        # HTML 注释 (<!-- Page X -->)
        if stripped.startswith("<!--") and stripped.endswith("-->"):
            flush()
            segments.append({"type": "non_text", "content": line})
            continue

        # 表格行
        if stripped.startswith("|") and stripped.endswith("|"):
            if not in_table:
                flush()
                buf_type = "non_text"
                in_table = True
            buf.append(line)
            continue
        else:
            if in_table:
                in_table = False
                flush()

        # 空行 — 段落分隔
        if not stripped:
            flush()
            continue

        # 普通文本行
        if buf_type == "non_text":
            flush()
        buf_type = "text"
        buf.append(line)

    flush()

    # 合并相邻的短文本段落
    merged: list[dict] = []
    for seg in segments:
        if (
            seg["type"] == "text"
            and merged
            and merged[-1]["type"] == "text"
            and len(merged[-1]["content"]) + len(seg["content"]) < 1500
        ):
            merged[-1]["content"] += "\n\n" + seg["content"]
        else:
            merged.append(seg)

    return merged


def _merge_text_blocks(blocks: list[ContentBlock], max_chars: int = 1500) -> list[ContentBlock]:
    """
    合并同一页的相邻小文本块，给 LLM 更多上下文，减少 API 调用次数。
    合并后的块保留第一个块的 y_pos，文本用双换行连接。
    """
    if not blocks:
        return []
    merged = []
    current = ContentBlock(
        type="text", y_pos=blocks[0].y_pos, text=blocks[0].text,
        font_size=blocks[0].font_size, is_bold=blocks[0].is_bold,
    )
    for b in blocks[1:]:
        if len(current.text) + len(b.text) < max_chars:
            current.text += "\n\n" + b.text
            current.font_size = max(current.font_size, b.font_size)
        else:
            merged.append(current)
            current = ContentBlock(
                type="text", y_pos=b.y_pos, text=b.text,
                font_size=b.font_size, is_bold=b.is_bold,
            )
    merged.append(current)
    return merged


@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    provider: str = Form("zhipuai"),
    model: str = Form("glm-4"),
    api_key: str | None = Form(None),
    system_prompt: str | None = Form(None),
    enable_ocr: bool = Form(False),
):
    logger.info(f"📄 上传: {file.filename} | LLM={provider}/{model} | OCR={'开' if enable_ocr else '关'}")

    if not file.filename or not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")

    actual_key = get_api_key(provider, api_key)
    if not actual_key:
        raise HTTPException(status_code=400, detail=f"API key required for provider: {provider}")

    manager = get_llm_manager()
    config = LLMConfig(provider=provider, model=model, api_key=actual_key)
    manager.register(FunctionKey.TRANSLATION, config)

    # 创建任务
    tm = get_task_manager()
    task_info = tm.create_task(file.filename or "unknown.pdf")

    Path("temp").mkdir(exist_ok=True)
    temp_path = Path(f"temp/{file.filename}")
    task_info.temp_path = temp_path

    async with aiofiles.open(temp_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    logger.info(f"   文件大小: {len(content) / 1024:.1f} KB | task_id={task_info.task_id}")

    try:
        job_start = time.time()

        async def llm_only_pipeline() -> str:
            """纯 LLM 管线：PyMuPDF 解析 → 分析摘要生成 prompt → 逐块翻译 → 组装 markdown"""
            t0 = time.time()
            logger.info("🔤 LLM 管线启动（PyMuPDF 解析）...")
            parser = PDFParser()
            translator = await TranslationService.from_manager(FunctionKey.TRANSLATION)
            builder = MarkdownBuilder()

            parsed = await parser.process(temp_path)
            total_pages = len(parsed.pages)
            logger.info(f"   PDF 解析完成: {total_pages} 页")

            # ── Step 0: 提取摘要 → 生成定制化翻译 prompt ──
            abstract_text = extract_abstract_from_blocks(parsed.pages)
            profile = await generate_prompt_profile(abstract_text, translator, system_prompt)
            final_prompt = profile.translation_prompt
            logger.info(f"📋 翻译 Prompt 已生成 | 领域: {profile.domain} | 术语: {len(profile.terminology)} 个")

            post_processor = PostProcessor()
            sem = asyncio.Semaphore(5)

            async def translate_block(block):
                async with sem:
                    block.text = await translator.translate(block.text, final_prompt)
                    block.text = post_processor.process(block.text)

            for idx, page in enumerate(parsed.pages):
                if task_info.cancelled:
                    raise asyncio.CancelledError("任务已被用户取消")

                page_start = time.time()
                text_blocks = [b for b in page.blocks if b.type == "text" and b.text.strip()]
                merged_blocks = _merge_text_blocks(text_blocks)

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
            logger.info(f"✅ LLM 管线完成 | {len(md)} 字符 | 耗时 {time.time() - t0:.1f}s")
            return md, images, profile

        async def ocr_translate_pipeline() -> str:
            """OCR + 翻译管线：OCR → markdown → 分析摘要生成 prompt → 分段翻译 → 重组"""
            t0 = time.time()
            logger.info("🔍 OCR + 翻译管线启动...")

            # Step 1: OCR 识别，得到完整 markdown（含图片、表格、公式）
            ocr_service = await OCRService.from_manager()
            ocr_md, ocr_images = await ocr_service.recognize(content, file_type=0)
            logger.info(f"   OCR 完成 | {len(ocr_md)} 字符 | 耗时 {time.time() - t0:.1f}s")

            if task_info.cancelled:
                raise asyncio.CancelledError("任务已被用户取消")

            # Step 1.5: 从 OCR markdown 中提取摘要 → 生成定制化翻译 prompt
            translator = await TranslationService.from_manager(FunctionKey.TRANSLATION)
            abstract_text = extract_abstract_from_markdown(ocr_md)
            profile = await generate_prompt_profile(abstract_text, translator, system_prompt)
            final_prompt = profile.translation_prompt
            logger.info(f"📋 翻译 Prompt 已生成 | 领域: {profile.domain} | 术语: {len(profile.terminology)} 个")

            if task_info.cancelled:
                raise asyncio.CancelledError("任务已被用户取消")

            # Step 2: 分段 — 区分文本段（需翻译）和非文本段（图片/表格/公式，保留原样）
            segments = _split_md_segments(ocr_md)
            text_segments = [s for s in segments if s["type"] == "text"]
            logger.info(f"   分段完成 | 总 {len(segments)} 段 | 文本 {len(text_segments)} 段待翻译")

            # Step 3: 并发翻译文本段
            post_processor = PostProcessor()
            sem = asyncio.Semaphore(5)
            translated_count = 0

            async def translate_segment(seg: dict):
                nonlocal translated_count
                async with sem:
                    if task_info.cancelled:
                        raise asyncio.CancelledError("任务已被用户取消")
                    original = seg["content"]
                    translated = await translator.translate(original, final_prompt)
                    translated = post_processor.process(translated)
                    seg["content"] = translated
                    translated_count += 1
                    if translated_count % 5 == 0 or translated_count == len(text_segments):
                        logger.info(
                            f"   翻译进度: [{translated_count}/{len(text_segments)}] "
                            f"{translated_count / len(text_segments) * 100:.0f}%"
                        )

            await asyncio.gather(*(translate_segment(s) for s in text_segments))

            # Step 4: 重组 — 按原始顺序拼接，非文本段原样保留
            parts = []
            for seg in segments:
                parts.append(seg["content"])
            result_md = "\n\n".join(parts)

            logger.info(f"✅ OCR + 翻译管线完成 | {len(result_md)} 字符 | 耗时 {time.time() - t0:.1f}s")
            return result_md, ocr_md, ocr_images, profile

        llm_images = {}
        ocr_images = {}

        if enable_ocr:
            ocr_mgr = get_ocr_manager()
            if ocr_mgr.has_binding("ocr"):
                pipeline_task = asyncio.create_task(ocr_translate_pipeline())
                task_info.asyncio_tasks = [pipeline_task]
                try:
                    llm_md, ocr_md, ocr_images, prompt_profile = await pipeline_task
                except asyncio.CancelledError:
                    logger.info(f"🛑 任务已取消: {task_info.task_id}")
                    raise HTTPException(status_code=499, detail="任务已取消")
            else:
                logger.warning("⚠️  OCR 已启用但未绑定 Provider，回退到 LLM 管线")
                llm_task = asyncio.create_task(llm_only_pipeline())
                task_info.asyncio_tasks = [llm_task]
                try:
                    llm_md, llm_images, prompt_profile = await llm_task
                except asyncio.CancelledError:
                    logger.info(f"🛑 任务已取消: {task_info.task_id}")
                    raise HTTPException(status_code=499, detail="任务已取消")
                ocr_md = None
        else:
            llm_task = asyncio.create_task(llm_only_pipeline())
            task_info.asyncio_tasks = [llm_task]
            try:
                llm_md, llm_images, prompt_profile = await llm_task
            except asyncio.CancelledError:
                logger.info(f"🛑 任务已取消: {task_info.task_id}")
                raise HTTPException(status_code=499, detail="任务已取消")
            ocr_md = None

        total_time = time.time() - job_start
        logger.info(f"🎉 任务完成 | 总耗时 {total_time:.1f}s")

        # 保存翻译结果到 Translation/{id}/ 文件夹
        store = get_translation_store()
        entry = await store.save(
            filename=file.filename or "output.pdf",
            translated_md=llm_md,
            images=llm_images,
            ocr_md=ocr_md,
            ocr_images=ocr_images,
            meta_extra={
                "provider": provider,
                "model": model,
                "enable_ocr": enable_ocr,
                "prompt_profile": {
                    "domain": prompt_profile.domain if prompt_profile else "",
                    "terminology_count": len(prompt_profile.terminology) if prompt_profile else 0,
                } if prompt_profile else None,
            },
        )

        translator = await TranslationService.from_manager(FunctionKey.TRANSLATION)
        return {
            "task_id": task_info.task_id,
            "translation_id": entry["id"],
            "markdown": llm_md,
            "ocr_markdown": ocr_md,
            "provider_used": translator.get_provider_name(),
            "model_used": model,
            "prompt_profile": {
                "domain": prompt_profile.domain if prompt_profile else "",
                "terminology_count": len(prompt_profile.terminology) if prompt_profile else 0,
                "keep_english": prompt_profile.keep_english if prompt_profile else [],
                "generated_prompt": prompt_profile.translation_prompt if prompt_profile else "",
            } if prompt_profile else None,
        }
    except HTTPException:
        raise
    except asyncio.CancelledError:
        raise HTTPException(status_code=499, detail="任务已取消")
    except Exception as e:
        logger.exception(f"❌ 处理失败: {e}")
        raise
    finally:
        tm.finish_task(task_info.task_id)


@router.post("/cancel/{task_id}")
async def cancel_task(task_id: str):
    """取消正在运行的翻译任务"""
    tm = get_task_manager()
    if tm.cancel_task(task_id):
        return {"message": f"任务 {task_id} 已取消"}
    raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在或已完成")


@router.post("/cancel-all")
async def cancel_all_tasks():
    """取消所有运行中的任务"""
    tm = get_task_manager()
    tm.cancel_all()
    return {"message": "所有任务已取消"}


@router.get("/tasks")
async def list_tasks():
    """列出当前运行中的任务"""
    tm = get_task_manager()
    return {"tasks": tm.list_tasks()}
