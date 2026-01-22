from .providers.base import BaseProvider, ProviderConfig
from .providers.glm import GLMProvider
from .providers.openai import OpenAIProvider
from .providers.deepseek import DeepSeekProvider
from typing import Dict, Optional


# Provider factory
PROVIDER_REGISTRY: Dict[str, type[BaseProvider]] = {
    "zhipuai": GLMProvider,
    "openai": OpenAIProvider,
    "deepseek": DeepSeekProvider,
}


def get_provider_for_model(model: str) -> type[BaseProvider]:
    """Get provider class based on model name"""
    if model.startswith("glm"):
        return GLMProvider
    elif model.startswith("gpt"):
        return OpenAIProvider
    elif model.startswith("deepseek"):
        return DeepSeekProvider
    else:
        return GLMProvider  # Default


class TranslationService:
    """Translation service with multi-provider support"""

    def __init__(self, provider_config: ProviderConfig, provider_override: Optional[str] = None):
        if provider_override:
            provider_class = PROVIDER_REGISTRY.get(provider_override)
            if not provider_class:
                provider_class = get_provider_for_model(provider_config.model)
            self.provider = provider_class(provider_config)
        else:
            provider_class = get_provider_for_model(provider_config.model)
            self.provider = provider_class(provider_config)

    async def translate(self, text: str) -> str:
        """Translate text maintaining markdown structure"""
        system_prompt = (
            "You are a professional academic translator. "
            "Translate the following content to Markdown format. "
            "Preserve all document structure, headings, lists, and formatting. "
            "For bilingual output, use format: [Original Text | Translation]"
        )
        return await self.provider.translate(text, system_prompt)

    def get_provider_name(self) -> str:
        """Get the name of the current provider"""
        return self.provider.provider_name
