"""OCRAgent — 文档解析 + 预处理 Agent

负责 PDF 解析/OCR 识别 → 跨页缝合 → 表格修复，输出干净的待翻译数据。
根据文档特征自动选择 LLM 管线（PyMuPDF）或 OCR 管线（PaddleOCR/MineRU）。

Requirements: 1.1, 1.2
"""

from __future__ import annotations

import logging
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.base import BaseAgent
from agent.context import AgentContext
from agent.registry import agent_registry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Document analysis helpers (moved from TranslationAgent)
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
    display_math = re.findall(r"\$\$.*?\$\$", text, re.DOTALL)
    inline_math = re.findall(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", text)
    return len(display_math) + len(inline_math), max(len(text), 1)


def _count_tables(text: str) -> int:
    lines = text.split("\n")
    table_count = 0
    i = 0
    while i < len(lines) - 1:
        line = lines[i].strip()
        next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if (
            line.startswith("|")
            and "|" in line[1:]
            and re.match(r"^\|[\s\-:|]+\|", next_line)
        ):
            table_count += 1
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                i += 1
            continue
        i += 1
    return table_count


def _detect_language_distribution(text: str) -> dict[str, float]:
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
# Cross-page stitching
# ---------------------------------------------------------------------------

# Sentence-ending punctuation (English + Chinese)
_SENTENCE_ENDINGS = re.compile(r"[.!?;:。！？；：\]\)）」』】]$")
# Patterns that indicate a line is a heading (not a continuation)
_HEADING_PATTERN = re.compile(r"^(?:#{1,6}\s|[A-Z][A-Z\s]{5,}$|\d+[\.\)]\s)")


def stitch_cross_page_blocks(pages: list) -> list:
    """合并跨页截断的文本块。

    启发式规则：
    - 当前页最后一个文本块不以终止符结尾
    - 下一页第一个文本块不像标题
    - 两个块字号相同（同属正文）
    """
    for i in range(len(pages) - 1):
        curr_page = pages[i]
        next_page = pages[i + 1]

        curr_texts = [b for b in curr_page.blocks if b.type == "text" and b.text.strip()]
        next_texts = [b for b in next_page.blocks if b.type == "text" and b.text.strip()]
        if not curr_texts or not next_texts:
            continue

        tail = curr_texts[-1]
        head = next_texts[0]

        tail_text = tail.text.rstrip()
        head_text = head.text.lstrip()

        # 尾块以终止符结尾 → 不是截断
        if _SENTENCE_ENDINGS.search(tail_text):
            continue

        # 头块像标题 → 不是截断
        if _HEADING_PATTERN.match(head_text):
            continue

        # 字号差异过大 → 不是同一段落
        if tail.font_size > 0 and head.font_size > 0:
            ratio = max(tail.font_size, head.font_size) / min(tail.font_size, head.font_size)
            if ratio > 1.15:
                continue

        # 合并
        logger.info(
            "Stitching cross-page blocks: page %d tail (%d chars) + page %d head (%d chars)",
            i + 1, len(tail_text), i + 2, len(head_text),
        )
        tail.text = tail_text + " " + head_text
        next_page.blocks.remove(head)

    return pages


# ---------------------------------------------------------------------------
# Cross-page table merging
# ---------------------------------------------------------------------------

def _count_columns(table_md: str) -> int:
    """Count columns in a markdown table string."""
    first_line = table_md.strip().split("\n")[0] if table_md.strip() else ""
    if not first_line.startswith("|"):
        return 0
    return len([c for c in first_line.split("|") if c.strip()]) 


def merge_cross_page_tables(pages: list) -> list:
    """合并跨页的 Markdown 表格。

    如果页 N 的最后一个表格和页 N+1 的第一个表格列数相同，
    且 N+1 的表格没有表头行（第二行不是分隔行），则合并。
    """
    for i in range(len(pages) - 1):
        curr_tables = pages[i].tables
        next_tables = pages[i + 1].tables
        if not curr_tables or not next_tables:
            continue

        tail_table = curr_tables[-1]
        head_table = next_tables[0]

        tail_cols = _count_columns(tail_table)
        head_cols = _count_columns(head_table)

        if tail_cols == 0 or tail_cols != head_cols:
            continue

        # 检查 head_table 是否有自己的表头（第二行是分隔行）
        head_lines = head_table.strip().split("\n")
        if len(head_lines) >= 2 and re.match(r"^\|[\s\-:|]+\|$", head_lines[1].strip()):
            # 有独立表头 → 是独立表格，不合并
            continue

        # 合并：把 head_table 的行追加到 tail_table
        logger.info(
            "Merging cross-page table: page %d (%d cols) + page %d (%d cols)",
            i + 1, tail_cols, i + 2, head_cols,
        )
        curr_tables[-1] = tail_table.rstrip() + "\n" + head_table.strip()
        next_tables.pop(0)

    return pages


# ---------------------------------------------------------------------------
# Table interleaving (fix table position by Y-coordinate)
# ---------------------------------------------------------------------------

def interleave_tables_into_blocks(pages: list) -> list:
    """将表格按 Y 坐标插入到文本块序列中，而不是追加到页面末尾。

    PyMuPDF 的 find_tables() 返回表格的 bbox，我们用 y_top 来确定插入位置。
    """
    try:
        import fitz
    except ImportError:
        return pages

    for page in pages:
        if not page.tables:
            continue

        # 表格已经是 markdown 字符串，没有位置信息
        # 目前 PDFParser._extract_tables 没有保存 bbox
        # 所以这里只能保持现有行为（表格追加到末尾）
        # TODO: 未来可以扩展 PDFParser 保存表格 bbox
        pass

    return pages


# ---------------------------------------------------------------------------
# OCR markdown preprocessing (cross-page stitch + table fix)
# ---------------------------------------------------------------------------

def stitch_ocr_paragraphs(ocr_md: str) -> str:
    """缝合 OCR Markdown 中被页面边界截断的段落。

    检测 <!-- Page X --> 注释附近的截断段落并合并。
    """
    lines = ocr_md.split("\n")
    result: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # 检测页面分隔注释
        if re.match(r"^\s*<!--\s*Page\s+\d+\s*-->", line.strip()):
            # 看前一个非空行是否被截断
            if result:
                # 找到前一个非空行
                prev_idx = len(result) - 1
                while prev_idx >= 0 and not result[prev_idx].strip():
                    prev_idx -= 1

                if prev_idx >= 0:
                    prev_line = result[prev_idx].rstrip()
                    # 前一行不以终止符结尾
                    if prev_line and not _SENTENCE_ENDINGS.search(prev_line):
                        # 找下一个非空行
                        j = i + 1
                        while j < len(lines) and not lines[j].strip():
                            j += 1

                        if j < len(lines):
                            next_line = lines[j].lstrip()
                            # 下一行不像标题
                            if not _HEADING_PATTERN.match(next_line):
                                # 合并：删除中间的空行和页面注释
                                result[prev_idx] = prev_line + " " + next_line
                                i = j + 1
                                continue

            result.append(line)
        else:
            result.append(line)
        i += 1

    return "\n".join(result)


def fix_ocr_tables(ocr_md: str) -> str:
    """修复 OCR 输出中残缺的 Markdown 表格。

    1. 为缺少分隔行的表格补充 |---|---|
    2. 修复列数不一致的行（补空列或截断多余列）
    """
    lines = ocr_md.split("\n")
    result: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 检测表格起始行
        if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 3:
            table_lines = [line]
            col_count = len([c for c in stripped.split("|") if c.strip()])
            i += 1

            # 检查下一行是否是分隔行
            has_separator = False
            while i < len(lines):
                next_stripped = lines[i].strip()
                if next_stripped.startswith("|") and next_stripped.endswith("|"):
                    if re.match(r"^\|[\s\-:|]+\|$", next_stripped):
                        has_separator = True
                    table_lines.append(lines[i])
                    i += 1
                else:
                    break

            # 如果没有分隔行，在第一行后插入
            if not has_separator and len(table_lines) >= 2:
                separator = "| " + " | ".join(["---"] * col_count) + " |"
                table_lines.insert(1, separator)

            # 修复列数不一致的行
            for idx, tline in enumerate(table_lines):
                tstripped = tline.strip()
                if not tstripped.startswith("|"):
                    continue
                cells = [c for c in tstripped.split("|") if c is not None]
                # 去掉首尾空字符串（split("|") 在 |a|b| 上产生 ['', 'a', 'b', '']）
                if cells and cells[0].strip() == "":
                    cells = cells[1:]
                if cells and cells[-1].strip() == "":
                    cells = cells[:-1]
                actual_cols = len(cells)

                if actual_cols < col_count:
                    cells.extend([""] * (col_count - actual_cols))
                    table_lines[idx] = "| " + " | ".join(c.strip() for c in cells) + " |"
                elif actual_cols > col_count:
                    cells = cells[:col_count]
                    table_lines[idx] = "| " + " | ".join(c.strip() for c in cells) + " |"

            result.extend(table_lines)
            continue

        result.append(line)
        i += 1

    return "\n".join(result)


# ---------------------------------------------------------------------------
# OCRAgent
# ---------------------------------------------------------------------------

NATIVE_TEXT_THRESHOLD = 200


@agent_registry.register
class OCRAgent(BaseAgent):
    """文档解析 + 预处理 Agent

    Workflow:
        1. 分析文档特征（扫描件/原生、公式密度、表格数量）
        2. 选择管线（LLM / OCR）
        3. 执行解析/OCR
        4. 跨页缝合 + 表格修复
        5. 输出干净的待翻译数据到 AgentContext

    输出:
        - LLM 管线: ctx.parsed_pdf (ParsedPDF)
        - OCR 管线: ctx.ocr_md (str), ctx.ocr_images (dict)
        - 两者: ctx.pipeline_type ("llm" | "ocr")
    """

    @property
    def name(self) -> str:
        return "ocr"

    @property
    def description(self) -> str:
        return "文档解析 + 预处理 Agent：解析/OCR → 跨页缝合 → 表格修复"

    async def run(self, input_data: AgentContext, **kwargs) -> AgentContext:
        ctx = input_data
        t0 = time.time()

        # auto_fix 场景：已有解析结果，跳过
        if ctx.pipeline_type and (ctx.parsed_pdf is not None or ctx.ocr_md):
            logger.info("Rerun detected: reusing existing parsed data, skipping OCR phase")
            await ctx.event_bus.publish(ctx.task_id, {
                "agent": "ocr",
                "stage": "skip",
                "progress": 10,
                "detail": {"message": "自动修正: 复用已有解析结果"},
            })
            return ctx

        # 1. 文档分析
        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "ocr",
            "stage": "analysis",
            "progress": 5,
            "detail": {"message": "分析文档特征..."},
        })
        doc_analysis = await self._analyze_document(ctx)
        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "ocr",
            "stage": "analysis",
            "progress": 8,
            "detail": {
                **doc_analysis.to_dict(),
                "message": (
                    f"文档分析: {'原生PDF' if doc_analysis.doc_type == 'native' else '扫描件'}, "
                    f"公式密度 {doc_analysis.formula_density:.4f}, 表格 {doc_analysis.table_count} 个"
                ),
            },
        })

        ctx.cancellation_token.check()

        # 2. 选择管线
        pipeline_type = self._select_pipeline(doc_analysis, ctx)
        ctx.pipeline_type = pipeline_type
        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "ocr",
            "stage": "pipeline_selection",
            "progress": 10,
            "detail": {
                "pipeline": pipeline_type,
                "message": f"选择管线: {'OCR + 翻译' if pipeline_type == 'ocr' else 'LLM 直接翻译'}",
            },
        })

        ctx.cancellation_token.check()

        # 3. 执行解析/OCR
        if pipeline_type == "ocr":
            await self._run_ocr_pipeline(ctx)
        else:
            await self._run_llm_parse(ctx)

        elapsed = time.time() - t0
        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "ocr",
            "stage": "complete",
            "progress": 25,
            "detail": {"message": f"文档解析 + 预处理完成 ({elapsed:.1f}s)"},
        })

        return ctx

    # ------------------------------------------------------------------
    # Document analysis (from TranslationAgent)
    # ------------------------------------------------------------------

    async def _analyze_document(self, ctx: AgentContext) -> DocumentAnalysis:
        analysis = DocumentAnalysis()
        extracted_text = ""

        try:
            import fitz

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

            if len(extracted_text.strip()) >= NATIVE_TEXT_THRESHOLD:
                analysis.doc_type = "native"
            else:
                analysis.doc_type = "scanned"

        except ImportError:
            logger.warning("PyMuPDF (fitz) not available, defaulting to 'scanned'")
            analysis.doc_type = "scanned"
        except Exception as e:
            logger.warning("Document analysis failed: %s, defaulting to 'scanned'", e)
            analysis.doc_type = "scanned"

        if extracted_text:
            formula_count, total_chars = _count_formulas(extracted_text)
            analysis.formula_density = round(formula_count / max(total_chars, 1), 6)
            analysis.table_count = _count_tables(extracted_text)
            analysis.language_distribution = _detect_language_distribution(extracted_text)
        else:
            analysis.language_distribution = {"en": 0.0, "zh": 0.0, "other": 0.0}

        logger.info(
            "Document analysis: type=%s, formulas=%.4f, tables=%d",
            analysis.doc_type, analysis.formula_density, analysis.table_count,
        )
        return analysis

    # ------------------------------------------------------------------
    # Pipeline selection (from TranslationAgent)
    # ------------------------------------------------------------------

    def _select_pipeline(self, doc_analysis: DocumentAnalysis, ctx: AgentContext) -> str:
        if ctx.enable_ocr:
            if self._is_ocr_available():
                logger.info("Pipeline selection: user requested OCR → ocr")
                return "ocr"
            else:
                logger.warning("Pipeline selection: user requested OCR but unavailable → llm (fallback)")
                return "llm"

        if doc_analysis.doc_type == "native":
            logger.info("Pipeline selection: native PDF → llm")
            return "llm"

        if self._is_ocr_available():
            logger.info("Pipeline selection: scanned PDF + OCR available → ocr")
            return "ocr"
        else:
            logger.info("Pipeline selection: scanned PDF but OCR unavailable → llm (fallback)")
            return "llm"

    def _is_ocr_available(self) -> bool:
        try:
            from backend.app.services.ocr_service import OCRService
            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # LLM parse path: PDFParser → stitch → table fix
    # ------------------------------------------------------------------

    async def _run_llm_parse(self, ctx: AgentContext) -> None:
        """PyMuPDF 解析 → 跨页缝合 → 跨页表格合并"""
        import aiofiles
        from backend.app.services.pdf_parser import PDFParser

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "ocr",
            "stage": "parsing",
            "progress": 12,
            "detail": {"message": "PyMuPDF 解析 PDF 中..."},
        })

        temp_path = Path(f"temp/{ctx.filename}")
        temp_path.parent.mkdir(exist_ok=True)
        async with aiofiles.open(temp_path, "wb") as f:
            await f.write(ctx.file_content)

        try:
            parser = PDFParser()
            parsed = await parser.process(temp_path)

            total_pages = len(parsed.pages)
            logger.info("PDF parsed: %d pages", total_pages)

            # 跨页缝合
            parsed.pages = stitch_cross_page_blocks(parsed.pages)
            # 跨页表格合并
            parsed.pages = merge_cross_page_tables(parsed.pages)

            ctx.parsed_pdf = parsed

            await ctx.event_bus.publish(ctx.task_id, {
                "agent": "ocr",
                "stage": "parsing",
                "progress": 22,
                "detail": {"message": f"PDF 解析完成: {total_pages} 页，已缝合跨页内容"},
            })
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # OCR path: OCR recognize → preprocess → stitch → table fix
    # ------------------------------------------------------------------

    async def _run_ocr_pipeline(self, ctx: AgentContext) -> None:
        """OCR 识别 → 预处理 → 跨页缝合 → 表格修复"""
        from backend.app.services.ocr_service import OCRService
        from backend.app.services.text_processing import preprocess_ocr_markdown

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "ocr",
            "stage": "ocr_recognizing",
            "progress": 12,
            "detail": {"message": "OCR 识别中..."},
        })

        ocr_service = await OCRService.from_manager()
        ocr_md, ocr_images = await ocr_service.recognize(ctx.file_content, file_type=0)

        logger.info("OCR complete: %d chars", len(ocr_md))

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "ocr",
            "stage": "preprocessing",
            "progress": 18,
            "detail": {"message": f"OCR 完成: {len(ocr_md)} 字符，预处理中..."},
        })

        ctx.cancellation_token.check()

        # 预处理：HTML table → MD table
        processed_md = preprocess_ocr_markdown(ocr_md)
        # 跨页段落缝合
        processed_md = stitch_ocr_paragraphs(processed_md)
        # 表格修复
        processed_md = fix_ocr_tables(processed_md)

        ctx.ocr_md = processed_md
        ctx.ocr_images = ocr_images or {}

        logger.info("OCR preprocessing complete: %d → %d chars", len(ocr_md), len(processed_md))

        await ctx.event_bus.publish(ctx.task_id, {
            "agent": "ocr",
            "stage": "preprocessing",
            "progress": 22,
            "detail": {"message": f"预处理完成: {len(processed_md)} 字符（缝合 + 表格修复）"},
        })
