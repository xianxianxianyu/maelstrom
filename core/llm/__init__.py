"""LLM Multiton 管理模块

按档案(profile) + 绑定(binding) 管理 LLM 实例，支持多 agent 场景。

用法:
    from core.llm import get_llm_manager, LLMConfig

    manager = get_llm_manager()
    manager.register_profile("my-deepseek", LLMConfig(provider="deepseek", model="deepseek-chat"))
    manager.bind("translation", "my-deepseek")
    instance = await manager.get("translation")
    result = await instance.complete("Hello", "Translate to Chinese")
"""
from .config import LLMConfig, FunctionKey
from .instance import LLMInstance
from .manager import LLMManager, get_llm_manager
from .loader import load_config_data, save_config_data, load_llm_configs

__all__ = [
    "LLMConfig",
    "FunctionKey",
    "LLMInstance",
    "LLMManager",
    "get_llm_manager",
    "load_config_data",
    "save_config_data",
    "load_llm_configs",
]
