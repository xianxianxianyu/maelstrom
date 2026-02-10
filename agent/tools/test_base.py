"""Unit tests for BaseTool ABC and ToolResult dataclass.

Validates:
- ToolResult dataclass fields and defaults (Requirements 5.4)
- BaseTool ABC interface enforcement (Requirements 5.2)
- Tool failure returns structured error info (Requirements 5.4)
"""

import pytest
from dataclasses import fields, asdict
from typing import Any

from agent.tools.base import BaseTool, ToolResult


# ---------------------------------------------------------------------------
# ToolResult tests
# ---------------------------------------------------------------------------

class TestToolResult:
    """Tests for the ToolResult dataclass."""

    def test_success_result_defaults(self):
        """A successful ToolResult should have sensible defaults."""
        result = ToolResult(success=True)
        assert result.success is True
        assert result.data is None
        assert result.error == ""
        assert result.recoverable is True

    def test_success_result_with_data(self):
        """ToolResult can carry arbitrary data on success."""
        result = ToolResult(success=True, data={"markdown": "# Hello"})
        assert result.success is True
        assert result.data == {"markdown": "# Hello"}
        assert result.error == ""

    def test_failure_result_recoverable(self):
        """A recoverable failure should have success=False, non-empty error, recoverable=True."""
        result = ToolResult(success=False, error="API timeout", recoverable=True)
        assert result.success is False
        assert result.error == "API timeout"
        assert result.recoverable is True
        assert result.data is None

    def test_failure_result_non_recoverable(self):
        """A non-recoverable failure should have recoverable=False."""
        result = ToolResult(success=False, error="Config missing", recoverable=False)
        assert result.success is False
        assert result.error == "Config missing"
        assert result.recoverable is False

    def test_toolresult_has_required_fields(self):
        """ToolResult must have exactly the four specified fields."""
        field_names = {f.name for f in fields(ToolResult)}
        assert field_names == {"success", "data", "error", "recoverable"}

    def test_toolresult_is_dataclass(self):
        """ToolResult should be a proper dataclass (supports asdict)."""
        result = ToolResult(success=True, data=[1, 2, 3], error="", recoverable=True)
        d = asdict(result)
        assert d == {
            "success": True,
            "data": [1, 2, 3],
            "error": "",
            "recoverable": True,
        }

    def test_toolresult_equality(self):
        """Two ToolResults with the same fields should be equal."""
        r1 = ToolResult(success=True, data="x")
        r2 = ToolResult(success=True, data="x")
        assert r1 == r2


# ---------------------------------------------------------------------------
# BaseTool ABC tests
# ---------------------------------------------------------------------------

class TestBaseTool:
    """Tests for the BaseTool abstract base class."""

    def test_cannot_instantiate_directly(self):
        """BaseTool is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            BaseTool()

    def test_concrete_tool_must_implement_all_abstract_members(self):
        """A subclass missing any abstract member cannot be instantiated."""

        class IncompleteTool(BaseTool):
            @property
            def name(self) -> str:
                return "incomplete"
            # missing description and execute

        with pytest.raises(TypeError):
            IncompleteTool()

    def test_concrete_tool_works(self):
        """A fully implemented subclass can be instantiated and has correct attributes."""

        class DummyTool(BaseTool):
            @property
            def name(self) -> str:
                return "dummy"

            @property
            def description(self) -> str:
                return "A dummy tool for testing"

            async def execute(self, **kwargs) -> ToolResult:
                return ToolResult(success=True, data="done")

        tool = DummyTool()
        assert tool.name == "dummy"
        assert tool.description == "A dummy tool for testing"

    @pytest.mark.asyncio
    async def test_concrete_tool_execute_returns_toolresult(self):
        """execute() should return a ToolResult instance."""

        class EchoTool(BaseTool):
            @property
            def name(self) -> str:
                return "echo"

            @property
            def description(self) -> str:
                return "Echoes input"

            async def execute(self, **kwargs) -> ToolResult:
                return ToolResult(success=True, data=kwargs.get("message"))

        tool = EchoTool()
        result = await tool.execute(message="hello")
        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.data == "hello"

    @pytest.mark.asyncio
    async def test_tool_failure_returns_structured_error(self):
        """When a tool fails, it should return structured error info (Req 5.4)."""

        class FailingTool(BaseTool):
            @property
            def name(self) -> str:
                return "failing"

            @property
            def description(self) -> str:
                return "Always fails"

            async def execute(self, **kwargs) -> ToolResult:
                try:
                    raise ConnectionError("Service unavailable")
                except ConnectionError as e:
                    return ToolResult(
                        success=False,
                        error=str(e),
                        recoverable=True,
                    )

        tool = FailingTool()
        result = await tool.execute()
        assert result.success is False
        assert result.error == "Service unavailable"
        assert isinstance(result.recoverable, bool)
        assert result.recoverable is True
