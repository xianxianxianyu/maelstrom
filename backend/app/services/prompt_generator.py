"""
Prompt Generator — 根据论文 Abstract 自动生成定制化翻译 Prompt

流程：
1. 从 PDF 中提取 Abstract（标题 + 摘要 + 前几段正文）
2. 发送给 LLM，让它分析论文领域、提取专业术语、生成翻译指令
3. 返回结构化的 PromptProfile，供后续翻译使用
"""
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PromptProfile:
    """LLM 生成的翻译配置"""
    domain: str = ""                          # 论文领域
    terminology: dict[str, str] = field(default_factory=dict)  # 术语表 {英文: 中文或保留原文}
    keep_english: list[str] = field(default_factory=list)      # 必须保留英文的术语
    translation_prompt: str = ""              # 最终生成的翻译 system prompt
    raw_analysis: str = ""                    # LLM 原始分析输出（调试用）


# 用于让 LLM 分析论文并生成翻译 prompt 的元提示
ANALYSIS_META_PROMPT = """\
You are an expert academic translation consultant. Analyze a paper's abstract and \
opening paragraphs, then produce a specialized translation configuration.

Output a JSON object with these fields:

1. "domain": The paper's research domain in Chinese (e.g. "自然语言处理 / 大语言模型推理优化")
2. "terminology": A dict of key technical terms. Key=English term, Value=Chinese translation \
or the English term itself if it should stay in English. Include 15-40 terms.
3. "keep_english": A list of terms that MUST stay in English (subset of terminology keys).
4. "style_notes": Special translation notes for this domain.

RULES:
- Output ONLY valid JSON, no markdown fences, no explanation.
- Include multi-word terms (e.g. "key-value cache", "attention state").

Paper excerpt:
---
{abstract_text}
---
"""


def _build_translation_prompt(profile: PromptProfile, user_base_prompt: Optional[str] = None) -> str:
    """根据 PromptProfile 组装最终的翻译 system prompt。"""
    term_lines = []
    for en, zh in profile.terminology.items():
        if en in profile.keep_english or en == zh:
            term_lines.append(f'  - {en} -> keep English "{en}"')
        else:
            term_lines.append(f"  - {en} -> {zh}")
    term_block = "\n".join(term_lines) if term_lines else "  (no special terms)"

    keep_en_list = ", ".join(profile.keep_english) if profile.keep_english else "none"

    domain_part = f" specializing in {profile.domain}" if profile.domain else ""

    parts = [
        f"You are a professional English-to-Chinese translator{domain_part}.",
        "",
        "TRANSLATION RULES:",
        "1. Translate the given English text into Chinese. Do NOT explain, summarize, or expand.",
        "2. Output format: original English paragraph first, then Chinese translation below. Separate with a blank line.",
        "3. Preserve ALL Markdown formatting: headings, bold, italic, lists, tables, math formulas, inline code.",
        "4. Do NOT add any content not in the original text.",
        "5. Do NOT wrap output in code fences.",
        "6. For short fragments (author names, affiliations, figure labels, references), translate directly.",
        "",
        "TERMINOLOGY GUIDE (follow strictly):",
        term_block,
        "",
        f"MUST KEEP IN ENGLISH: {keep_en_list}",
    ]

    if profile.domain:
        parts.append("")
        parts.append(
            f"DOMAIN CONTEXT: This paper is in {profile.domain}. "
            "Use standard technical Chinese. Prefer concise, precise translations."
        )

    return "\n".join(parts)


async def generate_prompt_profile(
    abstract_text: str,
    translator_service,
    user_base_prompt: Optional[str] = None,
) -> PromptProfile:
    """用 LLM 分析论文摘要，生成定制化翻译 prompt。"""
    profile = PromptProfile()

    if not abstract_text or len(abstract_text.strip()) < 50:
        logger.warning("摘要文本过短，跳过 prompt 生成，使用默认 prompt")
        profile.translation_prompt = _build_translation_prompt(profile, user_base_prompt)
        return profile

    excerpt = abstract_text[:3000]
    analysis_prompt = ANALYSIS_META_PROMPT.format(abstract_text=excerpt)

    try:
        logger.info("正在分析论文领域和术语...")
        raw = await translator_service.provider.translate(
            analysis_prompt,
            "You are a JSON-only output assistant. Output valid JSON with no extra text."
        )
        profile.raw_analysis = raw

        parsed = _parse_json_response(raw)
        if parsed:
            profile.domain = parsed.get("domain", "")
            profile.terminology = parsed.get("terminology", {})
            profile.keep_english = parsed.get("keep_english", [])
            logger.info(
                f"论文分析完成 | 领域: {profile.domain} | "
                f"术语: {len(profile.terminology)} 个 | "
                f"保留英文: {len(profile.keep_english)} 个"
            )
        else:
            logger.warning("LLM 返回的 JSON 解析失败，使用默认 prompt")

    except Exception as e:
        logger.warning(f"Prompt 生成失败: {e}，使用默认 prompt")

    profile.translation_prompt = _build_translation_prompt(profile, user_base_prompt)
    return profile


def _parse_json_response(raw: str) -> Optional[dict]:
    """从 LLM 输出中提取 JSON，容错处理。"""
    cleaned = raw.strip()
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None


def extract_abstract_from_blocks(pages) -> str:
    """从 PyMuPDF 解析的页面中提取 Abstract 部分（前两页文本）。"""
    texts = []
    for i, page in enumerate(pages):
        if i >= 2:
            break
        for block in page.blocks:
            if block.type == "text" and block.text.strip():
                texts.append(block.text.strip())
        if i == 0:
            texts.append("\n---\n")
    return "\n\n".join(texts)


def extract_abstract_from_markdown(md_text: str) -> str:
    """从 OCR markdown 中提取 Abstract 部分。"""
    lines = md_text.split("\n")
    abstract_start = -1
    abstract_end = len(lines)

    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        if abstract_start == -1:
            if (
                re.match(r'^#{1,3}\s*abstract', stripped)
                or stripped == "abstract"
                or stripped == "**abstract**"
            ):
                abstract_start = i
                continue
        if abstract_start != -1 and i > abstract_start:
            if re.match(r'^#{1,2}\s+\S', line.strip()) and not re.match(r'^#{1,3}\s*abstract', stripped):
                abstract_end = i
                break

    if abstract_start != -1:
        pre = "\n".join(lines[:abstract_start])
        body = "\n".join(lines[abstract_start:abstract_end])
        post = "\n".join(lines[abstract_end:abstract_end + 20])
        return f"{pre}\n\n{body}\n\n{post}"
    else:
        return md_text[:3000]
