"""MCP Gateway API — tool discovery, invocation, and resource providers."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from maelstrom.mcp.registry import get_registry
from maelstrom.mcp.schemas import ToolCall

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


@router.get("/tools")
async def list_tools(category: str | None = None):
    registry = get_registry()
    if category:
        tools = registry.list_tools_by_category(category)
    else:
        tools = registry.list_tools()
    return [t.model_dump() for t in tools]


@router.get("/tools/{tool_name}")
async def get_tool(tool_name: str):
    registry = get_registry()
    tool = registry.get_tool(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    return tool.model_dump()


@router.post("/tools/call")
async def call_tool(body: ToolCall):
    registry = get_registry()
    result = await registry.call_tool(body)
    return result.model_dump()


@router.get("/providers")
async def list_providers():
    registry = get_registry()
    return [p.model_dump() for p in registry.list_providers()]
