from openai import AsyncOpenAI
from .base import BaseProvider, ProviderConfig, ModelInfo


class OpenAIProvider(BaseProvider):
    """OpenAI provider implementation"""

    AVAILABLE_MODELS = [
        ModelInfo("gpt-4o", "GPT-4o", "openai", "Latest flagship model"),
        ModelInfo("gpt-4o-mini", "GPT-4o Mini", "openai", "Fast and cost-effective"),
        ModelInfo("gpt-4-turbo", "GPT-4 Turbo", "openai", "Previous flagship"),
    ]

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url
        )

    async def translate(self, text: str, system_prompt: str) -> str:
        """Translate using OpenAI API"""
        response = await self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        return response.choices[0].message.content

    def get_available_models(self) -> list[ModelInfo]:
        return self.AVAILABLE_MODELS

    @property
    def provider_name(self) -> str:
        return "openai"
