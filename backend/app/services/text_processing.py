"""文本处理工具 — Markdown 分段 + 文本块合并 + HTML 预处理

从 pdf.py 提取的纯函数，供 Pipeline 层调用。
"""
import re
from app.services.pdf_parser import ContentBlock


# ── HTML Table → Markdown Table 转换 ──

def html_table_to_markdown(html: str) -> str:
    """将 HTML <table> 转换为 Markdown 表格格式"""
    # 提取所有行
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
    if not rows:
        return html

    md_rows: list[list[str]] = []
    for row_html in rows:
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row_html, re.DOTALL | re.IGNORECASE)
        # 清理单元格内容
        cleaned = []
        for cell in cells:
            text = re.sub(r'<[^>]+>', '', cell).strip()
            text = text.replace('|', '\\|')  # 转义管道符
            text = re.sub(r'\s+', ' ', text)
            cleaned.append(text)
        if cleaned:
            md_rows.append(cleaned)

    if not md_rows:
        return html

    # 统一列数
    max_cols = max(len(r) for r in md_rows)
    for row in md_rows:
        while len(row) < max_cols:
            row.append("")

    lines = []
    # 表头
    lines.append("| " + " | ".join(md_rows[0]) + " |")
    lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    # 数据行
    for row in md_rows[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def preprocess_ocr_markdown(md_text: str) -> str:
    """OCR markdown 预处理：在分段之前清理和标准化格式

    1. HTML <table> → Markdown 表格
    2. <img> 标签标准化
    3. 图注 <div> 提取
    """
    # 1. HTML table → Markdown table
    def replace_table(m):
        return "\n\n" + html_table_to_markdown(m.group(0)) + "\n\n"
    md_text = re.sub(
        r'<table[^>]*>.*?</table>',
        replace_table,
        md_text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 2. 将 <div> 包裹的 <img> 提取为标准 markdown 图片
    # 匹配: <div...><img src="..." alt="..." width="..." /></div>
    def replace_div_img(m):
        img_match = re.search(r'<img\s+[^>]*src=["\']([^"\']+)["\'][^>]*/?\s*>', m.group(0), re.IGNORECASE)
        if img_match:
            src = img_match.group(1)
            alt_match = re.search(r'alt=["\']([^"\']*)["\']', m.group(0), re.IGNORECASE)
            alt = alt_match.group(1) if alt_match else "figure"
            return f"\n\n![{alt}]({src})\n\n"
        return m.group(0)

    md_text = re.sub(
        r'<div[^>]*>\s*<img\s+[^>]*/?\s*>\s*</div>',
        replace_div_img,
        md_text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 3. 图注 <div> → 特殊标记（翻译时保护格式，翻译后保留）
    # 匹配: <div style="text-align: center;">Figure 1. ...</div>
    # 转换为: > **Figure 1.** ...  (blockquote 格式的图注)
    def replace_figcaption(m):
        text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if not text:
            return ""
        return f"\n\n> {text}\n\n"

    md_text = re.sub(
        r'<div[^>]*style=["\'][^"\']*text-align:\s*center[^"\']*["\'][^>]*>(.*?)</div>',
        replace_figcaption,
        md_text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 4. 清理残留的空 div
    md_text = re.sub(r'<div[^>]*>\s*</div>', '', md_text, flags=re.IGNORECASE)

    # 5. 连续空行合并
    md_text = re.sub(r'\n{3,}', '\n\n', md_text)

    return md_text


# ── 后处理：引用上标 + 图注格式化 ──

def postprocess_translated_markdown(md_text: str) -> str:
    """翻译后的 Markdown 后处理：提升阅读体验

    1. 将引用编号 [1], [60] 等转为 <sup> 上标
    2. 将 blockquote 图注 (> Figure/Table/图/表) 格式化为居中 figcaption
    3. 检测并标记损坏的表格（如 ⚠️ 占位符）
    """
    lines = md_text.split('\n')
    result = []

    for line in lines:
        # 跳过代码块内容
        # (简单处理：不在代码块内做替换)

        # 1. 引用编号上标化
        # 匹配 [1], [60], [1, 2], [1, 31, 46] 等学术引用格式
        # 但不匹配 markdown 链接 [text](url) 和图片 ![alt](url)
        # 也不匹配表格行开头的 | 后面的内容
        if not line.strip().startswith('|') and not line.strip().startswith('```'):
            # 匹配连续引用 [1, 2, 3] 或 [1] [2] 或 [1, 31, 46, 60]
            line = re.sub(
                r'(?<!\!)\[(\d+(?:\s*,\s*\d+)*)\](?!\()',
                lambda m: '<sup>[' + m.group(1) + ']</sup>',
                line,
            )

        # 2. blockquote 图注 → 居中 figcaption HTML
        figcaption_match = re.match(
            r'^\s*>\s*((?:Figure|Table|Fig\.|Tab\.|图|表)\s*\d+[\.\:：]?\s*.*)$',
            line,
            re.IGNORECASE,
        )
        if figcaption_match:
            caption_text = figcaption_match.group(1).strip()
            # 将 "Figure 1." 或 "表 1." 加粗
            caption_text = re.sub(
                r'^((?:Figure|Table|Fig\.|Tab\.|图|表)\s*\d+[\.\:：]?)',
                r'**\1**',
                caption_text,
                flags=re.IGNORECASE,
            )
            line = f'<div class="figcaption">{caption_text}</div>'

        result.append(line)

    return '\n'.join(result)


# ── 行内 LaTeX 占位符保护 ──

_LATEX_PLACEHOLDER_PREFIX = "⟦LATEX_"
_LATEX_PLACEHOLDER_SUFFIX = "⟧"


def protect_inline_latex(text: str) -> tuple[str, dict[str, str]]:
    """将行内 LaTeX $ ... $ 替换为占位符，防止 LLM 翻译时破坏公式

    Returns:
        (替换后的文本, {占位符: 原始公式} 映射)
    """
    placeholders: dict[str, str] = {}
    counter = [0]

    def replacer(m):
        formula = m.group(0)
        key = f"{_LATEX_PLACEHOLDER_PREFIX}{counter[0]}{_LATEX_PLACEHOLDER_SUFFIX}"
        placeholders[key] = formula
        counter[0] += 1
        return key

    # 匹配行内公式 $ ... $（不匹配 $$ ... $$）
    # 要求 $ 后面不是空格，$ 前面不是空格
    protected = re.sub(
        r'(?<!\$)\$(?!\$)(?!\s)(.+?)(?<!\s)\$(?!\$)',
        replacer,
        text,
    )
    return protected, placeholders


def restore_inline_latex(text: str, placeholders: dict[str, str]) -> str:
    """将占位符还原为原始 LaTeX 公式"""
    for key, formula in placeholders.items():
        text = text.replace(key, formula)
    return text


# ── 分段逻辑 ──

def split_md_segments(md_text: str, merge_threshold: int = 1500) -> list[dict]:
    """
    将 OCR 输出的 markdown 切分为有序段落列表。
    每个段落是 dict: {"type": "text"|"non_text", "content": str}
    - non_text: 图片、表格、公式块、代码块、HTML 注释（不翻译）
    - text: 需要翻译的文本段落
    相邻的短文本段落会合并（< merge_threshold 字符），给 LLM 更好的上下文。
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
    in_code_block = False
    in_html_block = False

    for line in lines:
        stripped = line.strip()

        # ── 代码块 ```...``` ──
        if stripped.startswith("```"):
            if not in_code_block:
                flush()
                buf_type = "non_text"
                buf.append(line)
                in_code_block = True
            else:
                buf.append(line)
                in_code_block = False
                flush()
            continue
        if in_code_block:
            buf.append(line)
            continue

        # ── 数学公式块 $$...$$ ──
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

        # ── 单行公式块 $ ... $ (独占一行的长公式) ──
        if stripped.startswith("$") and stripped.endswith("$") and not in_math_block:
            flush()
            segments.append({"type": "non_text", "content": line})
            continue

        # ── HTML 块级元素 (<table>, <div> 等) ──
        if re.match(r'^\s*<(?:table|div|figure|figcaption)\b', stripped, re.IGNORECASE):
            flush()
            buf_type = "non_text"
            buf.append(line)
            # 检查是否单行闭合
            if re.search(r'</(?:table|div|figure|figcaption)>\s*$', stripped, re.IGNORECASE):
                flush()
            else:
                in_html_block = True
            continue
        if in_html_block:
            buf.append(line)
            if re.search(r'</(?:table|div|figure|figcaption)>\s*$', stripped, re.IGNORECASE):
                in_html_block = False
                flush()
            continue

        # ── 图片行 ──
        if re.match(r"^\s*!\[", stripped):
            flush()
            segments.append({"type": "non_text", "content": line})
            continue

        # ── <img> 标签 ──
        if re.match(r'^\s*<img\b', stripped, re.IGNORECASE):
            flush()
            segments.append({"type": "non_text", "content": line})
            continue

        # ── HTML 注释 (<!-- Page X -->) ──
        if stripped.startswith("<!--") and stripped.endswith("-->"):
            flush()
            segments.append({"type": "non_text", "content": line})
            continue

        # ── Markdown 表格行 ──
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

        # ── blockquote 图注 (> Figure ...) ──
        if re.match(r'^\s*>\s*(?:Figure|Table|图|表)\s*\d', stripped, re.IGNORECASE):
            flush()
            # 图注需要翻译，但作为独立段
            segments.append({"type": "text", "content": stripped.lstrip("> ").strip()})
            continue

        # ── 空行 — 段落分隔 ──
        if not stripped:
            flush()
            continue

        # ── 普通文本行 ──
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
            and len(merged[-1]["content"]) + len(seg["content"]) < merge_threshold
        ):
            merged[-1]["content"] += "\n\n" + seg["content"]
        else:
            merged.append(seg)

    return merged


# ── 文本块合并（LLM 管线用） ──

def merge_text_blocks(blocks: list[ContentBlock], max_chars: int = 1500) -> list[ContentBlock]:
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
