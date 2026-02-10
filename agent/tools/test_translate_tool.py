"""Unit tests for TranslateTool.

Validates:
- TranslateTool implements BaseTool interface correctly (Requirements 5.2)
- Successful translation returns ToolResult with translated_text (Requirements 5.3)
- PostProcessor is applied to raw translation output (Requirements 5.3)
- Custom system_prompt is forwarded to TranslationService (Requirements 5.3)
- Network/timeout errors return recoverable=True (Requirements 5.4)
- Config/setup errors return recoverable=False (Requirements 5.4)
- Missing or invalid arguments return structured errors (Requirements 5.4)
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agent.tools.base import BaseTool, ToolResult
from agent.tools.translate_tool import TranslateTool


# ---------------------------------------------------------------------------
# Interface tests
# ---------------------------------------------------------------------------


class TestTranslateToolInterface:
    """Tests that TranslateTool correctly implements the BaseTool ABC."""

    def test_is_subclass_of_base_tool(self):
        """TranslateTool should be a subclass of BaseTool."""
        assert issubclass(TranslateTool, BaseTool)

    def test_can_instantiate(self):
        """TranslateTool should be instantiable (all abstract members implemented)."""
        tool = TranslateTool()
        assert isinstance(tool, BaseTool)

    def test_name_property(self):
        """TranslateTool.name should return 'translate'."""
        tool = TranslateTool()
        assert tool.name == "translate"

    def test_description_property(self):
        """TranslateTool.description should return a non-empty string."""
        tool = TranslateTool()
        assert isinstance(tool.description, str)
        assert len(tool.description) > 0


# ---------------------------------------------------------------------------
# Success path tests
# ---------------------------------------------------------------------------


class TestTranslateToolSuccess:
    """Tests for successful translation execution."""

    @pytest.mark.asyncio
    async def test_successful_translation(self):
        """On success, execute() returns ToolResult with translated_text."""
        mock_service = AsyncMock()
        mock_service.translate.return_value = "这是翻译后的文本"

        mock_processor = MagicMock()
        mock_processor.process.return_value = "这是翻译后的文本"

        tool = TranslateTool()
        with patch(
            "agent.tools.translate_tool.TranslationService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ), patch(
            "agent.tools.translate_tool.PostProcessor",
            return_value=mock_processor,
        ):
            result = await tool.execute(text="This is the original text")

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.error == ""
        assert result.data == {"translated_text": "这是翻译后的文本"}

    @pytest.mark.asyncio
    async def test_post_processor_is_applied(self):
        """PostProcessor.process() should be called on the raw translation output."""
        mock_service = AsyncMock()
        mock_service.translate.return_value = "```markdown\n# 标题\n```"

        mock_processor = MagicMock()
        mock_processor.process.return_value = "# 标题"

        tool = TranslateTool()
        with patch(
            "agent.tools.translate_tool.TranslationService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ), patch(
            "agent.tools.translate_tool.PostProcessor",
            return_value=mock_processor,
        ):
            result = await tool.execute(text="# Title")

        mock_processor.process.assert_called_once_with("```markdown\n# 标题\n```")
        assert result.success is True
        assert result.data["translated_text"] == "# 标题"

    @pytest.mark.asyncio
    async def test_custom_system_prompt_forwarded(self):
        """Custom system_prompt should be passed to TranslationService.translate()."""
        mock_service = AsyncMock()
        mock_service.translate.return_value = "翻译结果"

        mock_processor = MagicMock()
        mock_processor.process.return_value = "翻译结果"

        custom_prompt = "You are a medical translator."
        tool = TranslateTool()
        with patch(
            "agent.tools.translate_tool.TranslationService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ), patch(
            "agent.tools.translate_tool.PostProcessor",
            return_value=mock_processor,
        ):
            result = await tool.execute(text="Patient symptoms", system_prompt=custom_prompt)

        mock_service.translate.assert_called_once_with("Patient symptoms", custom_prompt)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_default_system_prompt_when_not_provided(self):
        """When system_prompt is not provided, None should be passed to translate()."""
        mock_service = AsyncMock()
        mock_service.translate.return_value = "翻译结果"

        mock_processor = MagicMock()
        mock_processor.process.return_value = "翻译结果"

        tool = TranslateTool()
        with patch(
            "agent.tools.translate_tool.TranslationService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ), patch(
            "agent.tools.translate_tool.PostProcessor",
            return_value=mock_processor,
        ):
            result = await tool.execute(text="Hello world")

        mock_service.translate.assert_called_once_with("Hello world", None)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_service_called_with_text(self):
        """TranslationService.translate() should be called with the provided text."""
        mock_service = AsyncMock()
        mock_service.translate.return_value = "结果"

        mock_processor = MagicMock()
        mock_processor.process.return_value = "结果"

        tool = TranslateTool()
        input_text = "Some academic text to translate"
        with patch(
            "agent.tools.translate_tool.TranslationService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ), patch(
            "agent.tools.translate_tool.PostProcessor",
            return_value=mock_processor,
        ):
            await tool.execute(text=input_text)

        mock_service.translate.assert_called_once_with(input_text, None)


# ---------------------------------------------------------------------------
# Input validation tests
# ---------------------------------------------------------------------------


class TestTranslateToolInputValidation:
    """Tests for argument validation."""

    @pytest.mark.asyncio
    async def test_missing_text(self):
        """Calling execute() without text returns a non-recoverable error."""
        tool = TranslateTool()
        result = await tool.execute()

        assert result.success is False
        assert "text" in result.error
        assert result.recoverable is False

    @pytest.mark.asyncio
    async def test_invalid_text_type(self):
        """Passing a non-str text returns a non-recoverable error."""
        tool = TranslateTool()
        result = await tool.execute(text=12345)

        assert result.success is False
        assert "str" in result.error
        assert result.recoverable is False


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestTranslateToolErrorHandling:
    """Tests for exception handling and recoverable/non-recoverable classification."""

    @pytest.mark.asyncio
    async def test_connection_error_is_recoverable(self):
        """ConnectionError should result in recoverable=True."""
        mock_service = AsyncMock()
        mock_service.translate.side_effect = ConnectionError("Connection refused")

        tool = TranslateTool()
        with patch(
            "agent.tools.translate_tool.TranslationService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ):
            result = await tool.execute(text="test")

        assert result.success is False
        assert "Connection refused" in result.error
        assert result.recoverable is True

    @pytest.mark.asyncio
    async def test_timeout_error_is_recoverable(self):
        """TimeoutError should result in recoverable=True."""
        mock_service = AsyncMock()
        mock_service.translate.side_effect = TimeoutError("Request timed out")

        tool = TranslateTool()
        with patch(
            "agent.tools.translate_tool.TranslationService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ):
            result = await tool.execute(text="test")

        assert result.success is False
        assert "timed out" in result.error
        assert result.recoverable is True

    @pytest.mark.asyncio
    async def test_os_error_is_recoverable(self):
        """OSError (network-level) should result in recoverable=True."""
        mock_service = AsyncMock()
        mock_service.translate.side_effect = OSError("Network unreachable")

        tool = TranslateTool()
        with patch(
            "agent.tools.translate_tool.TranslationService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ):
            result = await tool.execute(text="test")

        assert result.success is False
        assert "Network unreachable" in result.error
        assert result.recoverable is True

    @pytest.mark.asyncio
    async def test_value_error_is_not_recoverable(self):
        """ValueError (config/setup issue) should result in recoverable=False."""
        mock_service = AsyncMock()
        mock_service.translate.side_effect = ValueError("Invalid configuration")

        tool = TranslateTool()
        with patch(
            "agent.tools.translate_tool.TranslationService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ):
            result = await tool.execute(text="test")

        assert result.success is False
        assert "Invalid configuration" in result.error
        assert result.recoverable is False

    @pytest.mark.asyncio
    async def test_runtime_error_is_not_recoverable(self):
        """RuntimeError should result in recoverable=False."""
        mock_service = AsyncMock()
        mock_service.translate.side_effect = RuntimeError("Provider not initialized")

        tool = TranslateTool()
        with patch(
            "agent.tools.translate_tool.TranslationService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ):
            result = await tool.execute(text="test")

        assert result.success is False
        assert "Provider not initialized" in result.error
        assert result.recoverable is False

    @pytest.mark.asyncio
    async def test_from_manager_failure_is_not_recoverable(self):
        """If TranslationService.from_manager() itself fails, it should be non-recoverable."""
        tool = TranslateTool()
        with patch(
            "agent.tools.translate_tool.TranslationService.from_manager",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Translation manager not configured"),
        ):
            result = await tool.execute(text="test")

        assert result.success is False
        assert "Translation manager not configured" in result.error
        assert result.recoverable is False

    @pytest.mark.asyncio
    async def test_from_manager_connection_error_is_recoverable(self):
        """If TranslationService.from_manager() raises ConnectionError, it should be recoverable."""
        tool = TranslateTool()
        with patch(
            "agent.tools.translate_tool.TranslationService.from_manager",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Cannot connect to translation service"),
        ):
            result = await tool.execute(text="test")

        assert result.success is False
        assert "Cannot connect to translation service" in result.error
        assert result.recoverable is True

    @pytest.mark.asyncio
    async def test_post_processor_error_is_not_recoverable(self):
        """If PostProcessor.process() raises an exception, it should be non-recoverable."""
        mock_service = AsyncMock()
        mock_service.translate.return_value = "翻译结果"

        mock_processor = MagicMock()
        mock_processor.process.side_effect = ValueError("Post-processing failed")

        tool = TranslateTool()
        with patch(
            "agent.tools.translate_tool.TranslationService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ), patch(
            "agent.tools.translate_tool.PostProcessor",
            return_value=mock_processor,
        ):
            result = await tool.execute(text="test")

        assert result.success is False
        assert "Post-processing failed" in result.error
        assert result.recoverable is False

    @pytest.mark.asyncio
    async def test_error_result_has_structured_fields(self):
        """All error results must have success=False, non-empty error, bool recoverable (Req 5.4)."""
        mock_service = AsyncMock()
        mock_service.translate.side_effect = Exception("Something went wrong")

        tool = TranslateTool()
        with patch(
            "agent.tools.translate_tool.TranslationService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ):
            result = await tool.execute(text="test")

        assert result.success is False
        assert isinstance(result.error, str)
        assert len(result.error) > 0
        assert isinstance(result.recoverable, bool)
