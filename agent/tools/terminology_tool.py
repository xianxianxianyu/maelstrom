"""TerminologyTool — 封装 GlossaryStore 的 CRUD 操作

将术语表管理能力封装为标准化的 BaseTool，供 Agent 调用。
通过 action 参数区分操作类型：query、update、merge、get_domain。

操作说明：
- query(term, domain?): 查询术语（支持模糊匹配）
- update(domain, english, chinese, source?): 更新或新增术语
- merge(domain, entries): 合并新术语到已有术语表
- get_domain(domain): 获取指定领域的完整术语表

异常处理策略：
- IO/网络错误 → recoverable=True（可重试）
- 参数/配置错误 → recoverable=False（不可恢复）

Requirements: 5.3
"""

import logging
from typing import Any

from agent.models import GlossaryEntry
from agent.tools.base import BaseTool, ToolResult
from agent.tools.glossary_store import GlossaryStore

logger = logging.getLogger(__name__)

# Exceptions considered recoverable (IO/transient issues)
_RECOVERABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
)

# Supported action names
_VALID_ACTIONS = frozenset({"query", "update", "merge", "get_domain"})


class TerminologyTool(BaseTool):
    """术语管理工具 — 封装 GlossaryStore 的查询/更新/合并操作"""

    def __init__(self, glossary_store: GlossaryStore | None = None) -> None:
        """初始化 TerminologyTool

        Args:
            glossary_store: 可选的 GlossaryStore 实例（用于依赖注入/测试）。
                           如果未提供，则创建默认的 GlossaryStore。
        """
        self._store = glossary_store or GlossaryStore()

    @property
    def name(self) -> str:
        return "terminology"

    @property
    def description(self) -> str:
        return "查询、更新和合并领域术语表，管理 Glossary 的 CRUD 操作"

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行术语管理操作

        Args:
            action (str): 操作类型，必需。取值：
                - "query": 查询术语，需要 term (str)，可选 domain (str)
                - "update": 更新术语，需要 domain (str)、english (str)、chinese (str)，可选 source (str)
                - "merge": 合并术语，需要 domain (str)、entries (list[dict])
                - "get_domain": 获取领域术语表，需要 domain (str)
            **kwargs: 操作相关的参数

        Returns:
            ToolResult: 执行结果
        """
        action: str | None = kwargs.get("action")

        # --- Validate action ---
        if action is None:
            return ToolResult(
                success=False,
                error="Missing required argument: action",
                recoverable=False,
            )

        if not isinstance(action, str):
            return ToolResult(
                success=False,
                error=f"action must be str, got {type(action).__name__}",
                recoverable=False,
            )

        if action not in _VALID_ACTIONS:
            return ToolResult(
                success=False,
                error=f"Unknown action: {action}",
                recoverable=False,
            )

        # --- Dispatch to action handler ---
        try:
            if action == "query":
                return await self._handle_query(**kwargs)
            elif action == "update":
                return await self._handle_update(**kwargs)
            elif action == "merge":
                return await self._handle_merge(**kwargs)
            elif action == "get_domain":
                return await self._handle_get_domain(**kwargs)
        except _RECOVERABLE_EXCEPTIONS as e:
            logger.warning("Terminology tool recoverable error: %s", e)
            return ToolResult(
                success=False,
                error=str(e),
                recoverable=True,
            )
        except Exception as e:
            logger.error("Terminology tool non-recoverable error: %s", e)
            return ToolResult(
                success=False,
                error=str(e),
                recoverable=False,
            )

        # Should not reach here, but just in case
        return ToolResult(
            success=False,
            error=f"Unknown action: {action}",
            recoverable=False,
        )

    async def _handle_query(self, **kwargs: Any) -> ToolResult:
        """处理 query 操作：查询术语（支持模糊匹配）"""
        term: str | None = kwargs.get("term")
        domain: str = kwargs.get("domain", "")

        if term is None:
            return ToolResult(
                success=False,
                error="Missing required argument for query: term",
                recoverable=False,
            )

        if not isinstance(term, str):
            return ToolResult(
                success=False,
                error=f"term must be str, got {type(term).__name__}",
                recoverable=False,
            )

        entries = await self._store.query(term, domain=domain)

        logger.info(
            "Terminology query '%s' (domain=%s): %d results",
            term,
            domain or "all",
            len(entries),
        )

        return ToolResult(
            success=True,
            data={"entries": [entry.to_dict() for entry in entries]},
        )

    async def _handle_update(self, **kwargs: Any) -> ToolResult:
        """处理 update 操作：更新或新增单个术语"""
        domain: str | None = kwargs.get("domain")
        english: str | None = kwargs.get("english")
        chinese: str | None = kwargs.get("chinese")
        source: str = kwargs.get("source", "user_edit")

        # Validate required arguments
        missing = []
        if domain is None:
            missing.append("domain")
        if english is None:
            missing.append("english")
        if chinese is None:
            missing.append("chinese")

        if missing:
            return ToolResult(
                success=False,
                error=f"Missing required argument(s) for update: {', '.join(missing)}",
                recoverable=False,
            )

        await self._store.update_entry(
            domain=domain,
            english=english,
            chinese=chinese,
            source=source,
        )

        logger.info(
            "Terminology updated [%s]: %s → %s",
            domain,
            english,
            chinese,
        )

        return ToolResult(
            success=True,
            data={"updated": True},
        )

    async def _handle_merge(self, **kwargs: Any) -> ToolResult:
        """处理 merge 操作：合并新术语到已有术语表"""
        domain: str | None = kwargs.get("domain")
        entries_data: list[dict] | None = kwargs.get("entries")

        # Validate required arguments
        missing = []
        if domain is None:
            missing.append("domain")
        if entries_data is None:
            missing.append("entries")

        if missing:
            return ToolResult(
                success=False,
                error=f"Missing required argument(s) for merge: {', '.join(missing)}",
                recoverable=False,
            )

        if not isinstance(entries_data, list):
            return ToolResult(
                success=False,
                error=f"entries must be a list, got {type(entries_data).__name__}",
                recoverable=False,
            )

        # Convert dicts to GlossaryEntry objects
        glossary_entries = [GlossaryEntry.from_dict(d) for d in entries_data]

        conflicts = await self._store.merge(domain, glossary_entries)

        # Load the merged entries to get the count
        merged = await self._store.load(domain)

        logger.info(
            "Terminology merge [%s]: %d entries merged, %d conflicts",
            domain,
            len(merged),
            len(conflicts),
        )

        return ToolResult(
            success=True,
            data={
                "conflicts": conflicts,
                "merged_count": len(merged),
            },
        )

    async def _handle_get_domain(self, **kwargs: Any) -> ToolResult:
        """处理 get_domain 操作：获取指定领域的完整术语表"""
        domain: str | None = kwargs.get("domain")

        if domain is None:
            return ToolResult(
                success=False,
                error="Missing required argument for get_domain: domain",
                recoverable=False,
            )

        if not isinstance(domain, str):
            return ToolResult(
                success=False,
                error=f"domain must be str, got {type(domain).__name__}",
                recoverable=False,
            )

        entries = await self._store.load(domain)

        logger.info(
            "Terminology get_domain [%s]: %d entries",
            domain,
            len(entries),
        )

        return ToolResult(
            success=True,
            data={"entries": [entry.to_dict() for entry in entries]},
        )
