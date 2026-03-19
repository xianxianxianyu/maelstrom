"""Intent classifier — keyword fast-path + LLM fallback."""
from __future__ import annotations

import asyncio
import json
import logging
import re

from maelstrom.schemas.intent import ClassifiedIntent, IntentType, SessionContext
from maelstrom.services.llm_client import call_llm
from maelstrom.services.llm_config_service import get_active_profile_dict

logger = logging.getLogger(__name__)

# ── Keyword patterns ─────────────────────────────────────────────────

_GAP_KEYWORDS = re.compile(
    r"研究空白|research\s*gap|gap\s*analysis|缺口|空白分析|survey|领域分析|研究方向|研究缺口|文献调研",
    re.IGNORECASE,
)

_QA_KEYWORDS = re.compile(
    r"这篇|论文|paper|文档|PDF|引用|摘要|abstract|方法是什么|结果是什么|实验|数据集",
    re.IGNORECASE,
)

_GAP_FOLLOWUP_PATTERNS = re.compile(
    r"gap-\d+|第[一二三四五六七八九十\d]+个\s*gap|展开|详细|elaborate|说说|解释一下",
    re.IGNORECASE,
)

_SHARE_KEYWORDS = re.compile(
    r"导入|share|加到问答|加入\s*QA|分享到|导出到",
    re.IGNORECASE,
)

_CONFIG_KEYWORDS = re.compile(
    r"配置|设置|切换.{0,10}模型|config|setting|API\s*key|模型切换|换个模型|换模型",
    re.IGNORECASE,
)

_SYNTHESIS_KEYWORDS = re.compile(
    r"文献综述|综述分析|可行性|feasibility|review\s*report|深入分析|立项评估|synthesis|做综述|写综述",
    re.IGNORECASE,
)

_PLANNING_KEYWORDS = re.compile(
    r"实验设计|实验规划|experiment\s*plan|ablation|baseline|做计划|写方案",
    re.IGNORECASE,
)

_EXPERIMENT_KEYWORDS = re.compile(
    r"跑实验|实验记录|run\s*experiment|实验结果|结论生成",
    re.IGNORECASE,
)

# Gap ref extraction
_GAP_REF_REGEX = re.compile(r"gap-(\d+)", re.IGNORECASE)
_GAP_ORDINAL_REGEX = re.compile(r"第([一二三四五六七八九十\d]+)个\s*gap", re.IGNORECASE)

_ORDINAL_MAP = {
    "一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
    "六": "6", "七": "7", "八": "8", "九": "9", "十": "10",
}


def _extract_gap_ref(text: str) -> str | None:
    m = _GAP_REF_REGEX.search(text)
    if m:
        return f"gap-{m.group(1)}"
    m = _GAP_ORDINAL_REGEX.search(text)
    if m:
        ordinal = m.group(1)
        num = _ORDINAL_MAP.get(ordinal, ordinal)
        return f"gap-{num}"
    return None


# ── Keyword classifier ───────────────────────────────────────────────


def _keyword_classify(
    user_input: str,
    context: SessionContext | None = None,
) -> ClassifiedIntent | None:
    text = user_input.strip()
    if not text:
        return None

    # gap_followup — check first (more specific)
    if _GAP_FOLLOWUP_PATTERNS.search(text):
        # Only classify as followup if session has gap runs or context suggests it
        if context and context.has_gap_runs:
            return ClassifiedIntent(
                intent=IntentType.gap_followup,
                confidence=0.85,
                extracted_gap_ref=_extract_gap_ref(text),
                classifier_source="keyword",
            )
        # If "gap-xxx" is explicitly mentioned, classify even without context
        if _GAP_REF_REGEX.search(text):
            return ClassifiedIntent(
                intent=IntentType.gap_followup,
                confidence=0.85,
                extracted_gap_ref=_extract_gap_ref(text),
                classifier_source="keyword",
            )

    # config
    if _CONFIG_KEYWORDS.search(text):
        return ClassifiedIntent(
            intent=IntentType.config,
            confidence=0.85,
            classifier_source="keyword",
        )

    # share_to_qa
    if _SHARE_KEYWORDS.search(text):
        return ClassifiedIntent(
            intent=IntentType.share_to_qa,
            confidence=0.85,
            classifier_source="keyword",
        )

    # synthesis — check before gap_discovery (overlapping keywords like 综述)
    if _SYNTHESIS_KEYWORDS.search(text):
        topic = _SYNTHESIS_KEYWORDS.sub("", text).strip().strip("，。,. 的")
        return ClassifiedIntent(
            intent=IntentType.synthesis,
            confidence=0.85,
            extracted_topic=topic if topic else None,
            classifier_source="keyword",
        )

    # planning
    if _PLANNING_KEYWORDS.search(text):
        topic = _PLANNING_KEYWORDS.sub("", text).strip().strip("，。,. 的")
        return ClassifiedIntent(
            intent=IntentType.planning,
            confidence=0.85,
            extracted_topic=topic if topic else None,
            classifier_source="keyword",
        )

    # experiment
    if _EXPERIMENT_KEYWORDS.search(text):
        topic = _EXPERIMENT_KEYWORDS.sub("", text).strip().strip("，。,. 的")
        return ClassifiedIntent(
            intent=IntentType.experiment,
            confidence=0.85,
            extracted_topic=topic if topic else None,
            classifier_source="keyword",
        )

    # gap_discovery — require minimum length
    if _GAP_KEYWORDS.search(text) and len(text) >= 10:
        # Extract topic: remove the keyword portion, keep the rest
        topic = _GAP_KEYWORDS.sub("", text).strip().strip("，。,. 的")
        return ClassifiedIntent(
            intent=IntentType.gap_discovery,
            confidence=0.85,
            extracted_topic=topic if topic else None,
            classifier_source="keyword",
        )

    # qa_chat
    if _QA_KEYWORDS.search(text):
        return ClassifiedIntent(
            intent=IntentType.qa_chat,
            confidence=0.85,
            classifier_source="keyword",
        )

    # Short question ending with ? — likely QA
    if len(text) < 50 and text.rstrip().endswith(("?", "？")):
        return ClassifiedIntent(
            intent=IntentType.qa_chat,
            confidence=0.75,
            classifier_source="keyword",
        )

    return None


# ── LLM classifier ──────────────────────────────────────────────────

_LLM_SYSTEM_PROMPT = """\
你是 Maelstrom 研究助手的意图分类器。根据用户输入，判断其意图类型。

可选意图：
- gap_discovery: 用户想发现研究缺口、分析研究空白、做文献调研
- qa_chat: 用户想对已有文档/论文提问
- gap_followup: 用户想追问已有的 Gap 分析结果
- share_to_qa: 用户想把 Gap 论文导入问答系统
- config: 用户想配置 LLM 或系统设置
- synthesis: 用户想做文献综述、可行性分析、立项评估
- planning: 用户想做实验设计、实验规划、写实验方案
- experiment: 用户想跑实验、记录实验结果、生成结论
- clarification_needed: 无法确定意图

会话上下文：
{context_info}

请输出 JSON（不要输出其他内容）：
{{"intent": "...", "confidence": 0.0-1.0, "extracted_topic": "...", "reasoning": "..."}}
"""


async def _llm_classify(
    user_input: str,
    context: SessionContext | None = None,
) -> ClassifiedIntent:
    context_info = "无会话上下文"
    if context:
        parts = []
        if context.has_gap_runs:
            parts.append("已有 Gap 分析结果")
        if context.has_indexed_docs:
            parts.append("已有索引文档")
        if context.recent_intent:
            parts.append(f"上一轮意图: {context.recent_intent.value}")
        context_info = "；".join(parts) if parts else "新会话，无历史"

    prompt = _LLM_SYSTEM_PROMPT.format(context_info=context_info) + f"\n用户输入：{user_input}"

    try:
        profile = get_active_profile_dict()
        raw = await asyncio.wait_for(
            call_llm(prompt, profile, max_tokens=256, temperature_override=0.1),
            timeout=10.0,
        )
        # Parse JSON from response
        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```\w*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned)
        data = json.loads(cleaned)

        intent_str = data.get("intent", "clarification_needed")
        try:
            intent = IntentType(intent_str)
        except ValueError:
            intent = IntentType.clarification_needed

        confidence = float(data.get("confidence", 0.5))
        if confidence < 0.6:
            intent = IntentType.clarification_needed

        return ClassifiedIntent(
            intent=intent,
            confidence=min(max(confidence, 0.0), 1.0),
            extracted_topic=data.get("extracted_topic"),
            reasoning=data.get("reasoning", ""),
            classifier_source="llm",
        )
    except (asyncio.TimeoutError, asyncio.CancelledError):
        logger.warning("LLM classifier timed out")
        return ClassifiedIntent(
            intent=IntentType.clarification_needed,
            confidence=0.0,
            reasoning="LLM classifier timed out",
            classifier_source="llm",
        )
    except Exception as e:
        logger.warning("LLM classifier failed: %s", e)
        return ClassifiedIntent(
            intent=IntentType.clarification_needed,
            confidence=0.0,
            reasoning=f"LLM classifier error: {e}",
            classifier_source="llm",
        )


# ── Public API ───────────────────────────────────────────────────────


async def classify_intent(
    user_input: str,
    session_context: SessionContext | None = None,
) -> ClassifiedIntent:
    """Classify user input intent. Keyword fast-path, then LLM fallback."""
    result = _keyword_classify(user_input, session_context)
    if result is not None:
        return result
    return await _llm_classify(user_input, session_context)
