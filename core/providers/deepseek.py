from .openai_compat import OpenAICompatProvider
from .base import ModelInfo


class DeepSeekProvider(OpenAICompatProvider):
    """DeepSeek provider (OpenAI-compatible API)"""

    DEFAULT_BASE_URL = "https://api.deepseek.com"

    AVAILABLE_MODELS = [
        ModelInfo("deepseek-chat", "DeepSeek Chat", "deepseek", "General conversation model"),
        ModelInfo("deepseek-reasoner", "DeepSeek Reasoner", "deepseek", "Advanced reasoning model"),
    ]

    @property
    def provider_name(self) -> str:
        return "deepseek"
