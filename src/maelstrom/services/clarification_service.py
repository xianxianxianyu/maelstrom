"""Clarification service — generate and resolve follow-up questions."""
from __future__ import annotations

import json
import logging
import re
import uuid

from maelstrom.schemas.clarification import ClarificationOption, ClarificationRequest
from maelstrom.schemas.intent import ClassifiedIntent, IntentType, SessionContext
from maelstrom.services.intent_classifier import classify_intent
from maelstrom.services.llm_client import call_llm
from maelstrom.services.llm_config_service import get_active_profile_dict

logger = logging.getLogger(__name__)

# Track clarification count per session to enforce max-1 rule
_clarification_counts: dict[str, int] = {}

# ── Default option sets ──────────────────────────────────────────────

_DEFAULT_OPTIONS = [
    ClarificationOption(
        label="发现研究缺口",
        intent=IntentType.gap_discovery,
        description="分析某个领域的研究空白和候选方向",
    ),
    ClarificationOption(
        label="文档问答",
        intent=IntentType.qa_chat,
        description="对已有论文或文档进行提问",
    ),
    ClarificationOption(
        label="系统设置",
        intent=IntentType.config,
        description="配置 LLM 模型或系统参数",
    ),
]


# ── Template clarification ───────────────────────────────────────────


def _build_template_clarification(
    original_input: str,
    session_id: str,
    top_options: list[ClarificationOption] | None = None,
) -> ClarificationRequest:
    options = top_options or _DEFAULT_OPTIONS[:3]
    question = f"我不太确定你的意图。你是想："
    return ClarificationRequest(
        request_id=str(uuid.uuid4()),
        question=question,
        options=options,
        allow_freetext=True,
        original_input=original_input,
        session_id=session_id,
    )


# ── LLM clarification ───────────────────────────────────────────────

_CLARIFICATION_PROMPT = """\
你是研究助手。用户输入不够明确，请生成一个友好的反问来澄清意图。

用户输入：{user_input}

请输出 JSON（不要输出其他内容）：
{{
  "question": "你的反问文本",
  "options": [
    {{"label": "选项1", "intent": "gap_discovery|qa_chat|config", "description": "说明"}},
    {{"label": "选项2", "intent": "gap_discovery|qa_chat|config", "description": "说明"}}
  ]
}}

选项数量 2-3 个，intent 必须是以下之一：gap_discovery, qa_chat, gap_followup, share_to_qa, config
"""


async def _llm_clarification(
    original_input: str,
    session_id: str,
) -> ClarificationRequest:
    try:
        profile = get_active_profile_dict()
        prompt = _CLARIFICATION_PROMPT.format(user_input=original_input)
        raw = await call_llm(prompt, profile, max_tokens=512, temperature_override=0.3)

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```\w*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned)
        data = json.loads(cleaned)

        options = []
        for opt in data.get("options", [])[:4]:
            try:
                intent = IntentType(opt["intent"])
            except (ValueError, KeyError):
                continue
            options.append(ClarificationOption(
                label=opt.get("label", ""),
                intent=intent,
                description=opt.get("description", ""),
            ))

        if len(options) < 2:
            return _build_template_clarification(original_input, session_id)

        return ClarificationRequest(
            request_id=str(uuid.uuid4()),
            question=data.get("question", "你想做什么？"),
            options=options,
            allow_freetext=True,
            original_input=original_input,
            session_id=session_id,
        )
    except Exception as e:
        logger.warning("LLM clarification failed: %s, falling back to template", e)
        return _build_template_clarification(original_input, session_id)


# ── Public API ───────────────────────────────────────────────────────


async def generate_clarification(
    original_input: str,
    session_id: str,
    confidence: float = 0.0,
) -> ClarificationRequest:
    """Generate a clarification request.

    Uses template for mid-confidence (0.4-0.6), LLM for low confidence.
    """
    _clarification_counts[session_id] = _clarification_counts.get(session_id, 0) + 1

    if 0.4 <= confidence <= 0.6:
        return _build_template_clarification(original_input, session_id)
    return await _llm_clarification(original_input, session_id)


async def resolve_clarification(
    session_id: str,
    request_id: str,
    option_index: int | None = None,
    freetext: str | None = None,
    options: list[ClarificationOption] | None = None,
) -> ClassifiedIntent:
    """Resolve a clarification reply into a ClassifiedIntent.

    If option_index is provided, map directly to the option's intent.
    If freetext is provided, re-classify (but enforce max-1 clarification).
    """
    # Option selection — direct mapping
    if option_index is not None and options and 0 <= option_index < len(options):
        selected = options[option_index]
        return ClassifiedIntent(
            intent=selected.intent,
            confidence=0.9,
            reasoning=f"User selected: {selected.label}",
            classifier_source="keyword",
        )

    # Freetext — re-classify, but check max clarification count
    if freetext:
        count = _clarification_counts.get(session_id, 0)
        if count >= 2:
            # Max clarifications reached — default to qa_chat
            return ClassifiedIntent(
                intent=IntentType.qa_chat,
                confidence=0.5,
                reasoning="Max clarifications reached, defaulting to qa_chat",
                classifier_source="keyword",
            )
        ctx = SessionContext(session_id=session_id, recent_intent=IntentType.clarification_needed)
        return await classify_intent(freetext, ctx)

    # Fallback — default to qa_chat
    return ClassifiedIntent(
        intent=IntentType.qa_chat,
        confidence=0.5,
        reasoning="No option or freetext provided, defaulting to qa_chat",
        classifier_source="keyword",
    )


def reset_clarification_count(session_id: str) -> None:
    """Reset clarification counter for a session (call after successful routing)."""
    _clarification_counts.pop(session_id, None)


def get_clarification_count(session_id: str) -> int:
    return _clarification_counts.get(session_id, 0)
