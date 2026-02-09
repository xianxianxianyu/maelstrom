from .pdf_parser import ParsedPDF, ContentBlock
from .base import BaseService
import base64


class MarkdownBuilder(BaseService[ParsedPDF]):
    async def process(self, parsed_pdf: ParsedPDF) -> tuple[str, dict[str, bytes]]:
        """
        按 Y 坐标顺序交织输出文本和图片，根据字号推断标题层级。
        返回 (markdown_str, images_dict)，图片使用相对路径 ./images/fig_N.ext
        """
        md_lines = []
        images: dict[str, bytes] = {}

        # 使用文档真实标题
        title = parsed_pdf.title or "Translated Document"
        md_lines.append(f"# {title}\n\n")

        # 收集所有文本块的字号，用于推断标题层级
        all_font_sizes = []
        for page in parsed_pdf.pages:
            for block in page.blocks:
                if block.type == "text" and block.font_size > 0:
                    all_font_sizes.append(block.font_size)

        # 计算字号阈值：正文字号 = 出现最多的字号
        body_size = _most_common_size(all_font_sizes) if all_font_sizes else 12.0

        global_img_idx = 0

        for page in parsed_pdf.pages:
            # 按 Y 坐标顺序输出内容块
            for block in page.blocks:
                if block.type == "text":
                    text = _apply_heading(block, body_size)
                    md_lines.append(text)
                    md_lines.append("\n\n")
                elif block.type == "image":
                    global_img_idx += 1
                    ext = block.image_ext or "png"
                    name = f"fig_{global_img_idx}.{ext}"
                    images[name] = block.image_bytes
                    md_lines.append(
                        f"![Figure {global_img_idx}](./images/{name})\n\n"
                    )

            # 表格单独输出
            for table_md in page.tables:
                md_lines.append(table_md)
                md_lines.append("\n\n")

        return "".join(md_lines), images


def _most_common_size(sizes: list[float]) -> float:
    """找出出现次数最多的字号（正文字号）"""
    from collections import Counter
    rounded = [round(s, 1) for s in sizes]
    counter = Counter(rounded)
    return counter.most_common(1)[0][0]


def _apply_heading(block: ContentBlock, body_size: float) -> str:
    """根据字号和加粗信息，给文本块添加 markdown 标题标记"""
    text = block.text.strip()
    if not text:
        return text

    # 已经有 markdown 标题标记的，不重复添加
    if text.startswith("#"):
        return text

    fs = block.font_size
    if fs <= 0:
        return text

    ratio = fs / body_size

    # 字号比正文大 60% 以上 → h2（h1 留给文档标题）
    if ratio >= 1.6:
        return f"## {text}"
    # 字号比正文大 25% 以上，或者加粗且比正文大 10% 以上 → h3
    if ratio >= 1.25 or (block.is_bold and ratio >= 1.1):
        return f"### {text}"
    # 加粗且字号略大 → h4
    if block.is_bold and ratio >= 1.0:
        return f"#### {text}"

    return text
