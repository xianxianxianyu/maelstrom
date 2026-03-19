"""MCP Tool Registry — register, discover, and call tools."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Coroutine

from maelstrom.mcp.schemas import ResourceProvider, ToolCall, ToolDefinition, ToolResult
from maelstrom.services.event_bus import get_event_bus

logger = logging.getLogger(__name__)

Handler = Callable[..., Coroutine[Any, Any, dict]]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolDefinition, Handler]] = {}
        self._providers: dict[str, ResourceProvider] = {}

    def register(self, definition: ToolDefinition, handler: Handler) -> None:
        self._tools[definition.name] = (definition, handler)

    def list_tools(self) -> list[ToolDefinition]:
        return [defn for defn, _ in self._tools.values()]

    def list_tools_by_category(self, category: str) -> list[ToolDefinition]:
        return [defn for defn, _ in self._tools.values() if defn.category == category]

    def get_tool(self, name: str) -> ToolDefinition | None:
        entry = self._tools.get(name)
        return entry[0] if entry else None

    async def call_tool(self, call: ToolCall) -> ToolResult:
        entry = self._tools.get(call.tool_name)
        if not entry:
            return ToolResult(tool_name=call.tool_name, success=False, error=f"Unknown tool: {call.tool_name}")

        defn, handler = entry
        bus = get_event_bus()
        await bus.emit("__mcp__", "tool_called", {"tool": call.tool_name, "arguments": call.arguments})

        t0 = time.monotonic()
        try:
            # Inject session_id if the handler accepts it and call provides it
            args = dict(call.arguments)
            if call.session_id and "session_id" not in args and "session_id" in defn.required_params:
                args["session_id"] = call.session_id
            output = await handler(**args)
            duration = (time.monotonic() - t0) * 1000
            return ToolResult(tool_name=call.tool_name, success=True, output=output, duration_ms=round(duration, 2))
        except Exception as e:
            duration = (time.monotonic() - t0) * 1000
            logger.exception("Tool %s failed", call.tool_name)
            return ToolResult(tool_name=call.tool_name, success=False, error=str(e), duration_ms=round(duration, 2))

    # ── Resource Providers ────────────────────────────────────────────

    def register_provider(self, provider: ResourceProvider) -> None:
        self._providers[provider.name] = provider

    def list_providers(self) -> list[ResourceProvider]:
        return list(self._providers.values())

    def get_provider(self, name: str) -> ResourceProvider | None:
        return self._providers.get(name)


# ── Singleton ────────────────────────────────────────────────────────

_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
