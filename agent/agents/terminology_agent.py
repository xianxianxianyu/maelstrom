"""TerminologyAgent — 术语管理 Agent

管理领域术语表：从文本中提取术语（通过 LLM）、查询、更新和合并术语。
支持四种操作：
- extract: 从文本提取术语并与 GlossaryStore 合并
- query: 查询术语（支持模糊匹配）
- update: 更新或新增单个术语
- merge: 合并新术语到已有术语表

Requirements: 3.1, 3.2, 3.3, 3.5, 3.6
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from agent.base import BaseAgent
from agent.models import GlossaryEntry
from agent.registry import agent_registry
from agent.tools.glossary_store import GlossaryStore
from agent.tools.terminology_tool import TerminologyTool

logger = logging.getLogger(__name__)

# Prompt template for LLM-based term extraction
_EXTRACT_PROMPT = """\
You are a terminology extraction expert for academic papers.
Analyze the following text and extract all domain-specific technical terms with their Chinese translations.

Return a JSON array of objects, each with:
- "english": the English term
- "chinese": the Chinese translation
- "keep_english": true if the English term should be kept in the translation (e.g., proper nouns, model names)

RULES:
1. Only extract domain-specific technical terms, not common English words.
2. For well-known model names and acronyms (e.g., Transformer, BERT, GPT), set keep_english=true.
3. Provide accurate, standard Chinese translations used in academic contexts.
4. Return ONLY the JSON array, no other text.

Text to analyze:
{text}
"""

# Valid actions for the TerminologyAgent
_VALID_ACTIONS = frozenset({"extract", "query", "update", "merge"})


def _parse_json_from_llm(response: str) -> list[dict]:
    """Parse JSON array from LLM response, handling markdown fences and partial JSON.

    Args:
        response: Raw LLM response text that may contain JSON wrapped in
                  markdown code fences or other surrounding text.

    Returns:
        Parsed list of dicts. Returns empty list if parsing fails.
    """
    text = response.strip()

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    fence_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
    match = fence_pattern.search(text)
    if match:
        text = match.group(1).strip()

    # Try to find a JSON array in the text
    # Look for the outermost [ ... ]
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        return []
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse JSON from LLM response: %s", text[:200])
        return []


@agent_registry.register
class TerminologyAgent(BaseAgent):
    """术语 Agent：管理领域术语表

    通过 LLM 从文本中提取术语，并提供术语的查询、更新和合并功能。
    所有持久化操作委托给 TerminologyTool / GlossaryStore。

    Attributes:
        _terminology_tool: 术语管理工具实例
        _glossary_store: 术语表存储实例
        _translation_service: 翻译服务实例（用于 LLM 调用），延迟初始化
    """

    def __init__(
        self,
        terminology_tool: TerminologyTool | None = None,
        glossary_store: GlossaryStore | None = None,
        translation_service: Any | None = None,
    ) -> None:
        """初始化 TerminologyAgent

        Args:
            terminology_tool: 可选的 TerminologyTool 实例（依赖注入）
            glossary_store: 可选的 GlossaryStore 实例（依赖注入）
            translation_service: 可选的 TranslationService 实例（依赖注入，
                                 用于测试时避免调用真实 LLM）
        """
        self._glossary_store = glossary_store or GlossaryStore()
        self._terminology_tool = terminology_tool or TerminologyTool(
            glossary_store=self._glossary_store
        )
        self._translation_service = translation_service

    @property
    def name(self) -> str:
        return "terminology"

    @property
    def description(self) -> str:
        return "术语 Agent：管理领域术语表"

    async def _get_translation_service(self) -> Any:
        """获取或创建 TranslationService 实例（延迟初始化）

        Returns:
            TranslationService 实例
        """
        if self._translation_service is None:
            from backend.app.services.translator import TranslationService

            self._translation_service = await TranslationService.from_manager()
        return self._translation_service

    async def run(self, input_data: Any, **kwargs) -> Any:
        """执行术语管理操作

        Args:
            input_data: 包含 action 字段的字典：
                - {"action": "extract", "text": str, "domain": str}
                - {"action": "query", "term": str, "domain"?: str}
                - {"action": "update", "domain": str, "english": str,
                   "chinese": str, "source"?: str}
                - {"action": "merge", "domain": str, "entries": list[dict]}

        Returns:
            操作结果字典

        Raises:
            ValueError: 当 input_data 不是字典或缺少 action 字段时
        """
        if not isinstance(input_data, dict):
            raise ValueError(
                f"input_data must be a dict, got {type(input_data).__name__}"
            )

        action = input_data.get("action")
        if action is None:
            raise ValueError("Missing required field: action")

        if action not in _VALID_ACTIONS:
            raise ValueError(
                f"Unknown action: {action}. Valid actions: {sorted(_VALID_ACTIONS)}"
            )

        if action == "extract":
            return await self._extract_terms(input_data)
        elif action == "query":
            return await self._query_term(input_data)
        elif action == "update":
            return await self._update_term(input_data)
        elif action == "merge":
            return await self._merge_glossary(input_data)

    async def _extract_terms(self, input_data: dict) -> dict:
        """从文本中提取术语并与 GlossaryStore 合并

        使用 LLM 分析文本，提取领域术语及其中文翻译，
        然后将提取的术语与已有 Glossary 合并。

        Args:
            input_data: {"action": "extract", "text": str, "domain": str}

        Returns:
            {"glossary": list[dict], "conflicts": list[dict]}
        """
        text = input_data.get("text", "")
        domain = input_data.get("domain", "general")

        if not text.strip():
            logger.warning("Empty text provided for term extraction")
            return {"glossary": [], "conflicts": []}

        # 截断过长文本，只用前 3000 字符做术语提取
        if len(text) > 3000:
            text = text[:3000]

        # Call LLM to extract terms
        logger.info("Calling LLM for terminology extraction (%d chars)...", len(text))
        prompt = _EXTRACT_PROMPT.format(text=text)
        svc = await self._get_translation_service()
        llm_response = await svc.translate(
            text=prompt,
            system_prompt="You are a terminology extraction assistant. Return only valid JSON.",
        )
        logger.info("LLM terminology extraction response received")

        # Parse LLM response
        raw_terms = _parse_json_from_llm(llm_response)
        if not raw_terms:
            logger.warning("LLM returned no extractable terms")
            return {"glossary": [], "conflicts": []}

        # Convert to GlossaryEntry objects
        new_entries: list[GlossaryEntry] = []
        for item in raw_terms:
            if not isinstance(item, dict):
                continue
            english = item.get("english", "").strip()
            chinese = item.get("chinese", "").strip()
            if not english or not chinese:
                continue
            new_entries.append(
                GlossaryEntry(
                    english=english,
                    chinese=chinese,
                    keep_english=bool(item.get("keep_english", False)),
                    domain=domain,
                    source="llm_extract",
                )
            )

        if not new_entries:
            logger.info("No valid terms extracted from LLM response")
            return {"glossary": [], "conflicts": []}

        # Merge with existing glossary
        conflicts = await self._glossary_store.merge(domain, new_entries)

        # Load the merged glossary to return
        merged_entries = await self._glossary_store.load(domain)
        glossary_dicts = [entry.to_dict() for entry in merged_entries]

        logger.info(
            "Extracted %d terms for domain '%s', %d conflicts",
            len(new_entries),
            domain,
            len(conflicts),
        )

        return {"glossary": glossary_dicts, "conflicts": conflicts}

    async def _query_term(self, input_data: dict) -> dict:
        """查询术语（委托给 TerminologyTool）

        Args:
            input_data: {"action": "query", "term": str, "domain"?: str}

        Returns:
            TerminologyTool 的查询结果
        """
        result = await self._terminology_tool.execute(
            action="query",
            term=input_data.get("term", ""),
            domain=input_data.get("domain", ""),
        )
        if result.success:
            return result.data
        else:
            raise RuntimeError(f"Query failed: {result.error}")

    async def _update_term(self, input_data: dict) -> dict:
        """更新术语（委托给 TerminologyTool）

        Args:
            input_data: {"action": "update", "domain": str, "english": str,
                         "chinese": str, "source"?: str}

        Returns:
            TerminologyTool 的更新结果
        """
        result = await self._terminology_tool.execute(
            action="update",
            domain=input_data.get("domain", ""),
            english=input_data.get("english", ""),
            chinese=input_data.get("chinese", ""),
            source=input_data.get("source", "user_edit"),
        )
        if result.success:
            return result.data
        else:
            raise RuntimeError(f"Update failed: {result.error}")

    async def _merge_glossary(self, input_data: dict) -> dict:
        """合并术语（委托给 TerminologyTool）

        Args:
            input_data: {"action": "merge", "domain": str, "entries": list[dict]}

        Returns:
            TerminologyTool 的合并结果
        """
        result = await self._terminology_tool.execute(
            action="merge",
            domain=input_data.get("domain", ""),
            entries=input_data.get("entries", []),
        )
        if result.success:
            return result.data
        else:
            raise RuntimeError(f"Merge failed: {result.error}")
