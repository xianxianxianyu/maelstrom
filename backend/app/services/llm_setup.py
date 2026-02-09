"""LLM 运行时配置服务 — 封装 LLMManager 的注册逻辑，路由层不再直接操作 Manager"""
import logging
from core.llm.manager import get_llm_manager
from core.llm.config import LLMConfig, FunctionKey

logger = logging.getLogger(__name__)


class LLMSetupService:
    """封装 LLM 配置的运行时注册逻辑"""

    @staticmethod
    def ensure_translation_ready(provider: str, model: str, api_key: str) -> None:
        """确保 translation 功能键已绑定到正确的 LLM 配置"""
        manager = get_llm_manager()
        config = LLMConfig(provider=provider, model=model, api_key=api_key)
        manager.register(FunctionKey.TRANSLATION, config)
        logger.info(f"已配置翻译 LLM: {provider}/{model}")

    @staticmethod
    def ensure_qa_ready(provider: str, model: str, api_key: str, **kwargs) -> None:
        """确保 QA 功能键已绑定到正确的 LLM 配置"""
        manager = get_llm_manager()
        config = LLMConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=kwargs.get("base_url"),
            temperature=kwargs.get("temperature", 0.3),
            max_tokens=kwargs.get("max_tokens", 4096),
        )
        manager.register(FunctionKey.QA, config)

    @staticmethod
    def ensure_ready(function_key: FunctionKey, provider: str, model: str, api_key: str, **kwargs) -> None:
        """通用：确保指定功能键已绑定"""
        manager = get_llm_manager()
        config = LLMConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=kwargs.get("base_url"),
            temperature=kwargs.get("temperature", 0.3),
            max_tokens=kwargs.get("max_tokens", 4096),
        )
        manager.register(function_key, config)
