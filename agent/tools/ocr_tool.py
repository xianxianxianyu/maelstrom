"""OCRTool — 封装 OCRService.recognize() 的 Agent 工具

将 OCR 识别能力封装为标准化的 BaseTool，供 Agent 调用。
输入 file_content (bytes)，输出 ToolResult(data={"markdown": str, "images": dict})。

异常处理策略：
- 网络/超时错误 → recoverable=True（可重试）
- 配置/设置错误 → recoverable=False（不可恢复）

Requirements: 5.3
"""

import logging
from typing import Any

from agent.tools.base import BaseTool, ToolResult
from backend.app.services.ocr_service import OCRService

logger = logging.getLogger(__name__)

# Exceptions considered recoverable (network/transient issues)
_RECOVERABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
)


class OCRTool(BaseTool):
    """OCR 识别工具 — 调用 OCRService 将文件内容转换为 Markdown + 图片"""

    @property
    def name(self) -> str:
        return "ocr"

    @property
    def description(self) -> str:
        return "调用 OCR 服务识别文件内容，返回 Markdown 文本和图片字典"

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行 OCR 识别

        Args:
            file_content (bytes): 待识别的文件内容（PDF 等）

        Returns:
            ToolResult: 成功时 data={"markdown": str, "images": dict[str, bytes]}
                        失败时 error=错误信息, recoverable=是否可重试
        """
        file_content: bytes | None = kwargs.get("file_content")

        if file_content is None:
            return ToolResult(
                success=False,
                error="Missing required argument: file_content",
                recoverable=False,
            )

        if not isinstance(file_content, bytes):
            return ToolResult(
                success=False,
                error=f"file_content must be bytes, got {type(file_content).__name__}",
                recoverable=False,
            )

        try:
            service = await OCRService.from_manager()
            markdown, images = await service.recognize(file_content)

            logger.info(
                "OCR recognition succeeded: %d chars markdown, %d images",
                len(markdown),
                len(images),
            )

            return ToolResult(
                success=True,
                data={"markdown": markdown, "images": images},
            )

        except _RECOVERABLE_EXCEPTIONS as e:
            logger.warning("OCR tool recoverable error: %s", e)
            return ToolResult(
                success=False,
                error=str(e),
                recoverable=True,
            )
        except Exception as e:
            logger.error("OCR tool non-recoverable error: %s", e)
            return ToolResult(
                success=False,
                error=str(e),
                recoverable=False,
            )
