"""ZhipuAI GLM provider — 同步 SDK，用 asyncio.to_thread 包装为异步"""
import asyncio
from zhipuai import ZhipuAI
from .base import BaseProvider, ProviderConfig, ModelInfo


class GLMProvider(BaseProvider):
    """ZhipuAI GLM provider

    ZhipuAI SDK 是同步的，通过 asyncio.to_thread 避免阻塞事件循环。
    """

    AVAILABLE_MODELS = [
        ModelInfo("glm-4", "GLM-4", "zhipuai", "Flagship model, best for translation"),
        ModelInfo("glm-4-flash", "GLM-4 Flash", "zhipuai", "Fast and cost-effective"),
        ModelInfo("glm-4v", "GLM-4V", "zhipuai", "Multimodal model with vision"),
    ]

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.client = ZhipuAI(
            api_key=config.api_key,
            base_url=config.base_url or "https://open.bigmodel.cn/api/paas/v4/"
        )

    def _sync_chat(self, messages: list[dict], **kwargs) -> str:
        """同步调用 ZhipuAI SDK"""
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=self.config.max_tokens,
        )
        return response.choices[0].message.content

    async def translate(self, text: str, system_prompt: str) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]
        return await asyncio.to_thread(self._sync_chat, messages)

    async def chat(self, messages: list[dict]) -> str:
        return await asyncio.to_thread(self._sync_chat, messages)

    def get_available_models(self) -> list[ModelInfo]:
        return self.AVAILABLE_MODELS

    @property
    def provider_name(self) -> str:
        return "zhipuai"
