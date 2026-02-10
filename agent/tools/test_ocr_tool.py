"""Unit tests for OCRTool.

Validates:
- OCRTool implements BaseTool interface correctly (Requirements 5.2)
- Successful OCR returns ToolResult with markdown and images (Requirements 5.3)
- Network/timeout errors return recoverable=True (Requirements 5.4)
- Config/setup errors return recoverable=False (Requirements 5.4)
- Missing or invalid arguments return structured errors (Requirements 5.4)
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agent.tools.base import BaseTool, ToolResult
from agent.tools.ocr_tool import OCRTool


# ---------------------------------------------------------------------------
# Interface tests
# ---------------------------------------------------------------------------


class TestOCRToolInterface:
    """Tests that OCRTool correctly implements the BaseTool ABC."""

    def test_is_subclass_of_base_tool(self):
        """OCRTool should be a subclass of BaseTool."""
        assert issubclass(OCRTool, BaseTool)

    def test_can_instantiate(self):
        """OCRTool should be instantiable (all abstract members implemented)."""
        tool = OCRTool()
        assert isinstance(tool, BaseTool)

    def test_name_property(self):
        """OCRTool.name should return 'ocr'."""
        tool = OCRTool()
        assert tool.name == "ocr"

    def test_description_property(self):
        """OCRTool.description should return a non-empty string."""
        tool = OCRTool()
        assert isinstance(tool.description, str)
        assert len(tool.description) > 0


# ---------------------------------------------------------------------------
# Success path tests
# ---------------------------------------------------------------------------


class TestOCRToolSuccess:
    """Tests for successful OCR execution."""

    @pytest.mark.asyncio
    async def test_successful_recognition(self):
        """On success, execute() returns ToolResult with markdown and images."""
        mock_service = AsyncMock()
        mock_service.recognize.return_value = (
            "# Title\n\nSome text",
            {"fig_1.png": b"png_data"},
        )

        tool = OCRTool()
        with patch(
            "agent.tools.ocr_tool.OCRService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ):
            result = await tool.execute(file_content=b"fake_pdf_bytes")

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.error == ""
        assert result.data["markdown"] == "# Title\n\nSome text"
        assert result.data["images"] == {"fig_1.png": b"png_data"}

    @pytest.mark.asyncio
    async def test_successful_recognition_empty_images(self):
        """OCR can succeed with no images extracted."""
        mock_service = AsyncMock()
        mock_service.recognize.return_value = ("Plain text content", {})

        tool = OCRTool()
        with patch(
            "agent.tools.ocr_tool.OCRService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ):
            result = await tool.execute(file_content=b"simple_pdf")

        assert result.success is True
        assert result.data["markdown"] == "Plain text content"
        assert result.data["images"] == {}

    @pytest.mark.asyncio
    async def test_service_called_with_file_content(self):
        """OCRService.recognize() should be called with the provided file_content."""
        mock_service = AsyncMock()
        mock_service.recognize.return_value = ("md", {})

        tool = OCRTool()
        file_bytes = b"test_content_123"
        with patch(
            "agent.tools.ocr_tool.OCRService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ):
            await tool.execute(file_content=file_bytes)

        mock_service.recognize.assert_called_once_with(file_bytes)


# ---------------------------------------------------------------------------
# Input validation tests
# ---------------------------------------------------------------------------


class TestOCRToolInputValidation:
    """Tests for argument validation."""

    @pytest.mark.asyncio
    async def test_missing_file_content(self):
        """Calling execute() without file_content returns a non-recoverable error."""
        tool = OCRTool()
        result = await tool.execute()

        assert result.success is False
        assert "file_content" in result.error
        assert result.recoverable is False

    @pytest.mark.asyncio
    async def test_invalid_file_content_type(self):
        """Passing a non-bytes file_content returns a non-recoverable error."""
        tool = OCRTool()
        result = await tool.execute(file_content="not_bytes")

        assert result.success is False
        assert "bytes" in result.error
        assert result.recoverable is False


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestOCRToolErrorHandling:
    """Tests for exception handling and recoverable/non-recoverable classification."""

    @pytest.mark.asyncio
    async def test_connection_error_is_recoverable(self):
        """ConnectionError should result in recoverable=True."""
        mock_service = AsyncMock()
        mock_service.recognize.side_effect = ConnectionError("Connection refused")

        tool = OCRTool()
        with patch(
            "agent.tools.ocr_tool.OCRService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ):
            result = await tool.execute(file_content=b"data")

        assert result.success is False
        assert "Connection refused" in result.error
        assert result.recoverable is True

    @pytest.mark.asyncio
    async def test_timeout_error_is_recoverable(self):
        """TimeoutError should result in recoverable=True."""
        mock_service = AsyncMock()
        mock_service.recognize.side_effect = TimeoutError("Request timed out")

        tool = OCRTool()
        with patch(
            "agent.tools.ocr_tool.OCRService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ):
            result = await tool.execute(file_content=b"data")

        assert result.success is False
        assert "timed out" in result.error
        assert result.recoverable is True

    @pytest.mark.asyncio
    async def test_os_error_is_recoverable(self):
        """OSError (network-level) should result in recoverable=True."""
        mock_service = AsyncMock()
        mock_service.recognize.side_effect = OSError("Network unreachable")

        tool = OCRTool()
        with patch(
            "agent.tools.ocr_tool.OCRService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ):
            result = await tool.execute(file_content=b"data")

        assert result.success is False
        assert "Network unreachable" in result.error
        assert result.recoverable is True

    @pytest.mark.asyncio
    async def test_value_error_is_not_recoverable(self):
        """ValueError (config/setup issue) should result in recoverable=False."""
        mock_service = AsyncMock()
        mock_service.recognize.side_effect = ValueError("Invalid configuration")

        tool = OCRTool()
        with patch(
            "agent.tools.ocr_tool.OCRService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ):
            result = await tool.execute(file_content=b"data")

        assert result.success is False
        assert "Invalid configuration" in result.error
        assert result.recoverable is False

    @pytest.mark.asyncio
    async def test_runtime_error_is_not_recoverable(self):
        """RuntimeError should result in recoverable=False."""
        mock_service = AsyncMock()
        mock_service.recognize.side_effect = RuntimeError("Provider not initialized")

        tool = OCRTool()
        with patch(
            "agent.tools.ocr_tool.OCRService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ):
            result = await tool.execute(file_content=b"data")

        assert result.success is False
        assert "Provider not initialized" in result.error
        assert result.recoverable is False

    @pytest.mark.asyncio
    async def test_from_manager_failure_is_not_recoverable(self):
        """If OCRService.from_manager() itself fails, it should be non-recoverable."""
        tool = OCRTool()
        with patch(
            "agent.tools.ocr_tool.OCRService.from_manager",
            new_callable=AsyncMock,
            side_effect=RuntimeError("OCR manager not configured"),
        ):
            result = await tool.execute(file_content=b"data")

        assert result.success is False
        assert "OCR manager not configured" in result.error
        assert result.recoverable is False

    @pytest.mark.asyncio
    async def test_from_manager_connection_error_is_recoverable(self):
        """If OCRService.from_manager() raises ConnectionError, it should be recoverable."""
        tool = OCRTool()
        with patch(
            "agent.tools.ocr_tool.OCRService.from_manager",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Cannot connect to OCR service"),
        ):
            result = await tool.execute(file_content=b"data")

        assert result.success is False
        assert "Cannot connect to OCR service" in result.error
        assert result.recoverable is True

    @pytest.mark.asyncio
    async def test_error_result_has_structured_fields(self):
        """All error results must have success=False, non-empty error, bool recoverable (Req 5.4)."""
        mock_service = AsyncMock()
        mock_service.recognize.side_effect = Exception("Something went wrong")

        tool = OCRTool()
        with patch(
            "agent.tools.ocr_tool.OCRService.from_manager",
            new_callable=AsyncMock,
            return_value=mock_service,
        ):
            result = await tool.execute(file_content=b"data")

        assert result.success is False
        assert isinstance(result.error, str)
        assert len(result.error) > 0
        assert isinstance(result.recoverable, bool)
