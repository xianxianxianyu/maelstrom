"""OpenAI 兼容 API 基类 — DeepSeek、OpenAI、Moonshot 等共用

子类只需定义 3 个类属性：
- DEFAULT_BASE_URL: API 地址
- AVAILABLE_MODELS: 可用模型列表
- provider_name: Provider 标识
"""
from openai import AsyncOpenAI
from .base import BaseProvider, ProviderConfig, ModelInfo


class OpenAICompatProvider(BaseProvider):
    """所有 OpenAI 兼容 API 的基类"""

    DEFAULT_BASE_URL: str = ""
    AVAILABLE_MODELS: list[ModelInfo] = []

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url or self.DEFAULT_BASE_URL or None,
            timeout=300.0,  # 翻译长文档需要较长超时
        )

    async def _chat_completion(self, messages: list[dict], **kwargs) -> str:
        """统一的 chat completion 调用"""
        params = {
            "model": self.config.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": self.config.max_tokens,
        }
        response = await self.client.chat.completions.create(**params)
        return response.choices[0].message.content

    async def translate(self, text: str, system_prompt: str) -> str:
        return await self._chat_completion([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ])

    async def chat(self, messages: list[dict]) -> str:
        return await self._chat_completion(messages)

    def get_available_models(self) -> list[ModelInfo]:
        return self.AVAILABLE_MODELS
