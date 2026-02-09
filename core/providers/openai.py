from .openai_compat import OpenAICompatProvider
from .base import ModelInfo


class OpenAIProvider(OpenAICompatProvider):
    """OpenAI provider"""

    AVAILABLE_MODELS = [
        ModelInfo("gpt-4o", "GPT-4o", "openai", "Latest flagship model"),
        ModelInfo("gpt-4o-mini", "GPT-4o Mini", "openai", "Fast and cost-effective"),
        ModelInfo("gpt-4-turbo", "GPT-4 Turbo", "openai", "Previous flagship"),
    ]

    @property
    def provider_name(self) -> str:
        return "openai"
