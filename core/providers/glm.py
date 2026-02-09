from zhipuai import ZhipuAI
from .base import BaseProvider, ProviderConfig, ModelInfo


class GLMProvider(BaseProvider):
    """ZhipuAI GLM provider implementation"""

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

    async def translate(self, text: str, system_prompt: str) -> str:
        """Translate using GLM API"""
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        return response.choices[0].message.content

    async def chat(self, messages: list[dict]) -> str:
        """Multi-turn chat using GLM API"""
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        return response.choices[0].message.content

    def get_available_models(self) -> list[ModelInfo]:
        return self.AVAILABLE_MODELS

    @property
    def provider_name(self) -> str:
        return "zhipuai"
