from openai import AsyncOpenAI
from .base import BaseProvider, ProviderConfig, ModelInfo


class DeepSeekProvider(BaseProvider):
    """DeepSeek provider implementation (OpenAI-compatible API)"""

    AVAILABLE_MODELS = [
        ModelInfo("deepseek-chat", "DeepSeek Chat", "deepseek", "General conversation model"),
        ModelInfo("deepseek-reasoner", "DeepSeek Reasoner", "deepseek", "Advanced reasoning model"),
    ]

    # Temperature for translation — low value for faithful output
    DEFAULT_TEMPERATURE = 0.3

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url or "https://api.deepseek.com"
        )

    async def translate(self, text: str, system_prompt: str) -> str:
        """Translate using DeepSeek API"""
        response = await self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=self.DEFAULT_TEMPERATURE,  # 1.3 for translation
            max_tokens=self.config.max_tokens,
            stream=False
        )
        return response.choices[0].message.content

    async def chat(self, messages: list[dict]) -> str:
        """Multi-turn chat using DeepSeek API"""
        response = await self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            stream=False
        )
        return response.choices[0].message.content

    def get_available_models(self) -> list[ModelInfo]:
        return self.AVAILABLE_MODELS

    @property
    def provider_name(self) -> str:
        return "deepseek"
