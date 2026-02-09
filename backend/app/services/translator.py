from core.providers.base import BaseProvider, ProviderConfig
from core.providers.glm import GLMProvider
from core.providers.openai import OpenAIProvider
from core.providers.deepseek import DeepSeekProvider
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

    SYSTEM_PROMPT = (
        "You are a professional English-to-Chinese translator for academic papers.\n"
        "RULES:\n"
        "1. Translate the given English text into Chinese. Do NOT explain, summarize, or expand the content.\n"
        "2. Output format: first the original English paragraph, then immediately below it the Chinese translation.\n"
        "3. Preserve all Markdown formatting: headings (#, ##, ###), bold, italic, lists, tables, math formulas.\n"
        "4. Do NOT add any content that is not in the original text.\n"
        "5. Do NOT wrap output in code fences.\n"
        "6. For short fragments (author names, figure labels, references), just translate directly without explanation.\n"
        "7. Keep proper nouns, model names, and technical terms (e.g. Transformer, KV Cache, LLM) in English within the Chinese translation.\n"
    )

    def __init__(self, provider_config: ProviderConfig = None, provider_override: Optional[str] = None,
                 llm_instance=None):
        """
        两种构造方式：
        1. 传统方式：provider_config + provider_override（向后兼容）
        2. 新方式：llm_instance（从 LLMManager 获取）
        """
        if llm_instance is not None:
            self._llm_instance = llm_instance
            self.provider = llm_instance.provider
        elif provider_config is not None:
            self._llm_instance = None
            if provider_override:
                provider_class = PROVIDER_REGISTRY.get(provider_override)
                if not provider_class:
                    provider_class = get_provider_for_model(provider_config.model)
                self.provider = provider_class(provider_config)
            else:
                provider_class = get_provider_for_model(provider_config.model)
                self.provider = provider_class(provider_config)
        else:
            raise ValueError("必须提供 provider_config 或 llm_instance")

    @classmethod
    async def from_manager(cls, function_key=None) -> "TranslationService":
        """从 LLMManager 创建 TranslationService"""
        from core.llm.manager import get_llm_manager
        from core.llm.config import FunctionKey
        key = function_key or FunctionKey.TRANSLATION
        instance = await get_llm_manager().get(key)
        return cls(llm_instance=instance)

    async def translate(self, text: str, system_prompt: str = None) -> str:
        """Translate text maintaining markdown structure"""
        prompt = system_prompt or self.SYSTEM_PROMPT
        return await self.provider.translate(text, prompt)

    def get_provider_name(self) -> str:
        """Get the name of the current provider"""
        return self.provider.provider_name
