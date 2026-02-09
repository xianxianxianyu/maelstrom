"""LLM 实例包装类，提供统一调用接口"""
import logging
from core.providers.base import BaseProvider
from .config import LLMConfig

logger = logging.getLogger(__name__)


class LLMInstance:
    """封装 Provider，提供 complete 和 chat 统一接口"""

    def __init__(self, config: LLMConfig, provider: BaseProvider):
        self.config = config
        self.provider = provider

    async def complete(self, prompt: str, system_prompt: str = "") -> str:
        """单轮调用（兼容现有 translate 接口）"""
        return await self.provider.translate(prompt, system_prompt)

    async def chat(self, messages: list[dict]) -> str:
        """多轮对话"""
        return await self.provider.chat(messages)

    @property
    def provider_name(self) -> str:
        return self.provider.provider_name
