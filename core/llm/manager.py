"""LLM Multiton 管理器 — 按档案(profile) + 绑定(binding) 管理 LLM 实例

与 backend 解耦：key_store 和 provider_registry 通过可选注入方式提供。
"""
import asyncio
import logging
from typing import Callable, Dict, Optional

from core.providers.base import BaseProvider
from core.providers.glm import GLMProvider
from core.providers.openai import OpenAIProvider
from core.providers.deepseek import DeepSeekProvider
from .config import FunctionKey, LLMConfig
from .instance import LLMInstance

logger = logging.getLogger(__name__)

# 实例数上限，防止内存泄漏
MAX_INSTANCES = 50

# 默认 Provider 注册表
DEFAULT_PROVIDER_REGISTRY: Dict[str, type[BaseProvider]] = {
    "zhipuai": GLMProvider,
    "openai": OpenAIProvider,
    "deepseek": DeepSeekProvider,
}


class LLMManager:
    """Multiton 管理器：支持命名档案(profile) + 功能绑定(binding)

    参数:
        key_resolver: 可选的 API Key 解析函数 (provider) -> key
        provider_registry: 可选的 Provider 注册表
    """

    def __init__(
        self,
        key_resolver: Optional[Callable[[str], Optional[str]]] = None,
        provider_registry: Optional[Dict[str, type[BaseProvider]]] = None,
    ):
        self._profiles: Dict[str, LLMConfig] = {}
        self._bindings: Dict[str, str] = {}
        self._instances: Dict[str, LLMInstance] = {}
        self._hashes: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._key_resolver = key_resolver
        self._provider_registry = provider_registry or DEFAULT_PROVIDER_REGISTRY

    # ── Key Resolver ──

    def set_key_resolver(self, resolver: Callable[[str], Optional[str]]) -> None:
        self._key_resolver = resolver

    def _resolve_key(self, provider: str) -> str:
        if self._key_resolver:
            return self._key_resolver(provider) or ""
        return ""

    # ── Profile 管理 ──

    def register_profile(self, name: str, config: LLMConfig) -> None:
        """注册命名档案"""
        self._profiles[name] = config
        # 清除该档案关联的所有实例缓存
        self._instances.pop(name, None)
        self._hashes.pop(name, None)
        logger.info(f"已注册 LLM 档案: {name} -> {config.provider}/{config.model}")

    def remove_profile(self, name: str) -> None:
        """移除命名档案及其实例"""
        self._profiles.pop(name, None)
        self._instances.pop(name, None)
        self._hashes.pop(name, None)
        # 清除引用该档案的 bindings
        to_remove = [k for k, v in self._bindings.items() if v == name]
        for k in to_remove:
            del self._bindings[k]
        logger.info(f"已移除 LLM 档案: {name}")

    def get_all_profiles(self) -> Dict[str, LLMConfig]:
        return dict(self._profiles)

    def get_profile(self, name: str) -> Optional[LLMConfig]:
        return self._profiles.get(name)

    # ── Binding 管理 ──

    def bind(self, function_key: str, profile_name: str) -> None:
        """绑定功能键到档案名"""
        self._bindings[function_key] = profile_name

    def get_all_bindings(self) -> Dict[str, str]:
        return dict(self._bindings)

    def set_bindings(self, bindings: Dict[str, str]) -> None:
        self._bindings = dict(bindings)

    # ── 向后兼容的 register / get ──

    def register(self, function_key, config: LLMConfig) -> None:
        """向后兼容：注册功能键 = 创建同名 profile + 自绑定"""
        key = function_key.value if isinstance(function_key, FunctionKey) else str(function_key)
        self.register_profile(key, config)
        self.bind(key, key)

    async def get(self, function_key) -> LLMInstance:
        """通过功能键获取 LLM 实例（先查 binding -> profile -> 创建实例）"""
        key = function_key.value if isinstance(function_key, FunctionKey) else str(function_key)

        # 通过 binding 查找 profile 名
        profile_name = self._bindings.get(key, key)
        config = self._profiles.get(profile_name)
        if not config:
            raise KeyError(f"功能键 '{key}' 绑定的档案 '{profile_name}' 不存在")

        runtime_key = config.api_key or self._resolve_key(config.provider)
        current_hash = config.config_hash(runtime_key)

        cache_key = f"{key}:{profile_name}"
        if cache_key in self._instances and self._hashes.get(cache_key) == current_hash:
            return self._instances[cache_key]

        async with self._lock:
            if cache_key in self._instances and self._hashes.get(cache_key) == current_hash:
                return self._instances[cache_key]

            if len(self._instances) >= MAX_INSTANCES and cache_key not in self._instances:
                raise RuntimeError(f"LLM 实例数已达上限 ({MAX_INSTANCES})")

            provider_class = self._provider_registry.get(config.provider)
            if not provider_class:
                raise ValueError(f"未知的 Provider: {config.provider}")

            if not runtime_key:
                raise ValueError(f"档案 '{profile_name}' 的 Provider '{config.provider}' 缺少 API Key")

            provider_config = config.to_provider_config(runtime_key)
            provider = provider_class(provider_config)
            instance = LLMInstance(config, provider)

            self._instances[cache_key] = instance
            self._hashes[cache_key] = current_hash
            logger.info(f"已创建 LLM 实例: {key} -> {profile_name} ({config.provider}/{config.model})")
            return instance

    # ── 查询方法 ──

    def get_config(self, function_key) -> Optional[LLMConfig]:
        key = function_key.value if isinstance(function_key, FunctionKey) else str(function_key)
        profile_name = self._bindings.get(key, key)
        return self._profiles.get(profile_name)

    def get_all_configs(self) -> Dict[str, LLMConfig]:
        """向后兼容：返回所有 profiles"""
        return dict(self._profiles)

    def list_functions(self) -> list[str]:
        return list(self._bindings.keys())

    def reset(self) -> None:
        self._profiles.clear()
        self._bindings.clear()
        self._instances.clear()
        self._hashes.clear()
        logger.info("LLMManager 已重置")


# 模块级单例
_manager: Optional[LLMManager] = None


def get_llm_manager() -> LLMManager:
    global _manager
    if _manager is None:
        _manager = LLMManager()
    return _manager
