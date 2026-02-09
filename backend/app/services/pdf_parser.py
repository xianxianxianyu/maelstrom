import fitz  # PyMuPDF
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Set
from .base import BaseService


@dataclass
class ContentBlock:
    """页面内容块（文本或图片），按 Y 坐标排序"""
    type: str          # "text" | "image"
    y_pos: float       # 页面中的 Y 坐标（用于排序）
    text: str = ""     # type=text 时的文本内容
    image_bytes: bytes = b""  # type=image 时的图片数据
    image_ext: str = "png"    # 图片格式（png/jpeg/...）
    font_size: float = 0      # 最大字号（用于判断标题）
    is_bold: bool = False     # 是否加粗


@dataclass
class PDFPage:
    page_number: int
    blocks: List[ContentBlock] = field(default_factory=list)
    tables: List[str] = field(default_factory=list)


@dataclass
class ParsedPDF:
    pages: List[PDFPage]
    metadata: dict
    title: str = ""


class PDFParser(BaseService[Path]):
    # 页面顶部/底部百分比阈值，用于检测页眉页脚
    HEADER_FOOTER_RATIO = 0.05

    async def process(self, pdf_path: Path) -> ParsedPDF:
        """结构化提取 PDF 内容：文本带字体信息 + 图片带位置"""
        doc = fitz.open(pdf_path)
        pages = []

        # 收集跨页重复文本用于页眉页脚检测
        repeated_texts = self._find_repeated_texts(doc)

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_height = page.rect.height
            blocks = []

            # 提取结构化文本块
            text_blocks = self._extract_text_blocks(
                page, page_height, repeated_texts
            )
            blocks.extend(text_blocks)

            # 提取图片块（带位置信息）
            image_blocks = self._extract_image_blocks(page)
            blocks.extend(image_blocks)

            # 按 Y 坐标排序，实现图文交织
            blocks.sort(key=lambda b: b.y_pos)

            # 提取表格
            tables = self._extract_tables(page)

            pages.append(PDFPage(page_num + 1, blocks, tables))

        # 提取文档标题
        title = self._extract_title(doc, pages)

        metadata = doc.metadata if hasattr(doc, 'metadata') else {}
        doc.close()
        return ParsedPDF(pages, metadata, title)

    def _find_repeated_texts(self, doc) -> Set[str]:
        """找出跨页重复的短文本（疑似页眉页脚）"""
        if len(doc) < 3:
            return set()

        page_texts: List[Set[str]] = []
        for page_num in range(min(len(doc), 10)):
            page = doc[page_num]
            page_height = page.rect.height
            header_y = page_height * self.HEADER_FOOTER_RATIO
            footer_y = page_height * (1 - self.HEADER_FOOTER_RATIO)

            edge_texts = set()
            dict_data = page.get_text("dict")
            for block in dict_data.get("blocks", []):
                if block.get("type") != 0:
                    continue
                bbox = block.get("bbox", (0, 0, 0, 0))
                y_top = bbox[1]
                y_bottom = bbox[3]
                # 只看页面边缘区域的文本
                if y_top < header_y or y_bottom > footer_y:
                    for line in block.get("lines", []):
                        line_text = ""
                        for span in line.get("spans", []):
                            line_text += span.get("text", "")
                        line_text = line_text.strip()
                        if line_text and len(line_text) < 100:
                            edge_texts.add(line_text)
            page_texts.append(edge_texts)

        # 在 3 页以上出现的边缘文本视为页眉页脚
        if len(page_texts) < 3:
            return set()
        repeated = set()
        all_texts = set()
        for texts in page_texts:
            all_texts.update(texts)
        for text in all_texts:
            count = sum(1 for texts in page_texts if text in texts)
            if count >= min(3, len(page_texts)):
                repeated.add(text)
        return repeated

    def _extract_text_blocks(
        self, page, page_height: float, repeated_texts: Set[str]
    ) -> List[ContentBlock]:
        """从页面提取结构化文本块"""
        header_y = page_height * self.HEADER_FOOTER_RATIO
        footer_y = page_height * (1 - self.HEADER_FOOTER_RATIO)

        blocks = []
        dict_data = page.get_text("dict")

        for block in dict_data.get("blocks", []):
            if block.get("type") != 0:  # 只处理文本块
                continue

            bbox = block.get("bbox", (0, 0, 0, 0))
            y_pos = bbox[1]

            # 收集该块所有行的文本
            block_text = ""
            max_font_size = 0
            has_bold = False

            for line in block.get("lines", []):
                line_text = ""
                for span in line.get("spans", []):
                    span_text = span.get("text", "")
                    line_text += span_text
                    font_size = span.get("size", 0)
                    if font_size > max_font_size:
                        max_font_size = font_size
                    flags = span.get("flags", 0)
                    if flags & 2 ** 4:  # bold flag
                        has_bold = True
                block_text += line_text + "\n"

            block_text = block_text.strip()
            if not block_text:
                continue

            # 跳过页眉页脚区域的重复文本
            if block_text in repeated_texts:
                if y_pos < header_y or (bbox[3] > footer_y):
                    continue

            blocks.append(ContentBlock(
                type="text",
                y_pos=y_pos,
                text=block_text,
                font_size=max_font_size,
                is_bold=has_bold,
            ))

        return blocks

    def _extract_image_blocks(self, page) -> List[ContentBlock]:
        """提取图片及其在页面中的位置"""
        blocks = []
        image_list = page.get_images(full=True)

        for img_info in image_list:
            xref = img_info[0]
            try:
                base_image = page.parent.extract_image(xref)
                if not base_image:
                    continue
                image_bytes = base_image["image"]
                image_ext = base_image.get("ext", "png")

                # 获取图片在页面中的位置
                y_pos = self._get_image_y_pos(page, xref)

                blocks.append(ContentBlock(
                    type="image",
                    y_pos=y_pos,
                    image_bytes=image_bytes,
                    image_ext=image_ext,
                ))
            except Exception:
                continue

        return blocks

    def _get_image_y_pos(self, page, xref: int) -> float:
        """获取图片在页面中的 Y 坐标"""
        # 遍历页面内容查找图片位置
        for img_info in page.get_image_info():
            if img_info.get("xref") == xref:
                bbox = img_info.get("bbox", (0, 0, 0, 0))
                return bbox[1]  # y_top
        # 找不到位置则放在页面中间
        return page.rect.height / 2

    def _extract_tables(self, page) -> List[str]:
        """提取表格并转为 markdown 格式"""
        tables = []
        try:
            found_tables = page.find_tables()
            for table in found_tables:
                md = self._table_to_markdown(table.extract())
                if md:
                    tables.append(md)
        except Exception:
            pass
        return tables

    def _table_to_markdown(self, table_data: list) -> str:
        """将表格数据转为 markdown 表格"""
        if not table_data or len(table_data) < 1:
            return ""

        rows = []
        for row in table_data:
            cells = [str(cell).strip() if cell else "" for cell in row]
            rows.append("| " + " | ".join(cells) + " |")

        if len(rows) < 1:
            return ""

        # 在第一行后插入分隔行
        header = rows[0]
        col_count = header.count("|") - 1
        separator = "| " + " | ".join(["---"] * col_count) + " |"

        result = [header, separator] + rows[1:]
        return "\n".join(result)

    def _extract_title(self, doc, pages: List[PDFPage]) -> str:
        """从 metadata 或首页提取文档标题"""
        # 优先从 metadata 获取
        if hasattr(doc, 'metadata') and doc.metadata:
            title = doc.metadata.get("title", "")
            if title and title.strip():
                return title.strip()

        # 从首页最大字号文本块推断标题
        if pages and pages[0].blocks:
            text_blocks = [b for b in pages[0].blocks if b.type == "text"]
            if text_blocks:
                largest = max(text_blocks, key=lambda b: b.font_size)
                if largest.font_size > 0 and len(largest.text) < 200:
                    return largest.text.split("\n")[0].strip()

        return ""
