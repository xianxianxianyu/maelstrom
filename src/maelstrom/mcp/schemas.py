"""MCP schemas — tool definitions, calls, results, and resource providers."""
from __future__ import annotations

from pydantic import BaseModel


class ToolDefinition(BaseModel):
    name: str
    description: str
    category: str = "general"
    input_schema: dict = {}
    required_params: list[str] = []


class ToolCall(BaseModel):
    tool_name: str
    arguments: dict = {}
    session_id: str | None = None


class ToolResult(BaseModel):
    tool_name: str
    success: bool = True
    output: dict = {}
    error: str | None = None
    duration_ms: float = 0.0


class ResourceProvider(BaseModel):
    """Describes an external resource provider (MCP profile)."""
    name: str
    provider_type: str  # e.g. "paper_search", "web_search", "dataset", "file_system"
    description: str = ""
    config: dict = {}
    enabled: bool = True
