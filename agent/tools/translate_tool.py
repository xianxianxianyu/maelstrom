"""TranslateTool — 封装 TranslationService.translate() + PostProcessor.process()

将 LLM 翻译能力封装为标准化的 BaseTool，供 Agent 调用。
输入 text (str) 和可选的 system_prompt (str)，
输出 ToolResult(data={"translated_text": str})。

异常处理策略：
- 网络/超时错误 → recoverable=True（可重试）
- 配置/设置错误 → recoverable=False（不可恢复）

Requirements: 5.3
"""

import logging
from typing import Any

from agent.tools.base import BaseTool, ToolResult
from backend.app.services.translator import TranslationService
from backend.app.services.post_processor import PostProcessor

logger = logging.getLogger(__name__)

# Exceptions considered recoverable (network/transient issues)
_RECOVERABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
)


class TranslateTool(BaseTool):
    """翻译工具 — 调用 TranslationService 翻译文本并通过 PostProcessor 后处理"""

    @property
    def name(self) -> str:
        return "translate"

    @property
    def description(self) -> str:
        return "调用 LLM 翻译服务将文本翻译为中文，并进行格式后处理"

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行翻译

        Args:
            text (str): 待翻译的文本（必需）
            system_prompt (str, optional): 自定义系统 prompt，覆盖默认翻译 prompt

        Returns:
            ToolResult: 成功时 data={"translated_text": str}
                        失败时 error=错误信息, recoverable=是否可重试
        """
        text: str | None = kwargs.get("text")
        system_prompt: str | None = kwargs.get("system_prompt")

        # --- Input validation ---
        if text is None:
            return ToolResult(
                success=False,
                error="Missing required argument: text",
                recoverable=False,
            )

        if not isinstance(text, str):
            return ToolResult(
                success=False,
                error=f"text must be str, got {type(text).__name__}",
                recoverable=False,
            )

        try:
            service = await TranslationService.from_manager()
            raw_translation = await service.translate(text, system_prompt)

            processor = PostProcessor()
            translated_text = processor.process(raw_translation)

            logger.info(
                "Translation succeeded: %d chars input → %d chars output",
                len(text),
                len(translated_text),
            )

            return ToolResult(
                success=True,
                data={"translated_text": translated_text},
            )

        except _RECOVERABLE_EXCEPTIONS as e:
            logger.warning("Translate tool recoverable error: %s", e)
            return ToolResult(
                success=False,
                error=str(e),
                recoverable=True,
            )
        except Exception as e:
            logger.error("Translate tool non-recoverable error: %s", e)
            return ToolResult(
                success=False,
                error=str(e),
                recoverable=False,
            )
