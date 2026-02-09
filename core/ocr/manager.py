"""OCR Multiton 管理器 — 按档案(profile) + 绑定(binding) 管理 OCR 实例

与 LLMManager 设计模式一致，但完全独立。
"""
import asyncio
import logging
from typing import Callable, Dict, Optional

from .config import OCRConfig, OCRFunctionKey
from .providers.base import BaseOCRProvider
from .providers.paddleocr import PaddleOCRProvider
from .providers.mineru import MineRUProvider

logger = logging.getLogger(__name__)

MAX_INSTANCES = 20

DEFAULT_OCR_PROVIDER_REGISTRY: Dict[str, type[BaseOCRProvider]] = {
    "paddleocr": PaddleOCRProvider,
    "mineru": MineRUProvider,
}


class OCRManager:
    """OCR Multiton 管理器：支持命名档案 + 功能绑定"""

    def __init__(
        self,
        key_resolver: Optional[Callable[[str], Optional[str]]] = None,
        provider_registry: Optional[Dict[str, type[BaseOCRProvider]]] = None,
    ):
        self._profiles: Dict[str, OCRConfig] = {}
        self._bindings: Dict[str, str] = {}
        self._instances: Dict[str, BaseOCRProvider] = {}
        self._hashes: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._key_resolver = key_resolver
        self._provider_registry = provider_registry or DEFAULT_OCR_PROVIDER_REGISTRY

    def set_key_resolver(self, resolver: Callable[[str], Optional[str]]) -> None:
        self._key_resolver = resolver

    def _resolve_key(self, provider: str) -> str:
        if self._key_resolver:
            return self._key_resolver(provider) or ""
        return ""

    # ── Profile 管理 ──

    def register_profile(self, name: str, config: OCRConfig) -> None:
        self._profiles[name] = config
        self._instances.pop(name, None)
        self._hashes.pop(name, None)
        logger.info(f"已注册 OCR 档案: {name} -> {config.provider}/{config.mode}")

    def remove_profile(self, name: str) -> None:
        self._profiles.pop(name, None)
        self._instances.pop(name, None)
        self._hashes.pop(name, None)
        to_remove = [k for k, v in self._bindings.items() if v == name]
        for k in to_remove:
            del self._bindings[k]

    def get_all_profiles(self) -> Dict[str, OCRConfig]:
        return dict(self._profiles)

    def get_profile(self, name: str) -> Optional[OCRConfig]:
        return self._profiles.get(name)

    # ── Binding 管理 ──

    def bind(self, function_key: str, profile_name: str) -> None:
        self._bindings[function_key] = profile_name

    def get_all_bindings(self) -> Dict[str, str]:
        return dict(self._bindings)

    def set_bindings(self, bindings: Dict[str, str]) -> None:
        self._bindings = dict(bindings)

    # ── 实例获取 ──

    async def get(self, function_key) -> BaseOCRProvider:
        """通过功能键获取 OCR Provider 实例"""
        key = function_key.value if isinstance(function_key, OCRFunctionKey) else str(function_key)

        profile_name = self._bindings.get(key, key)
        config = self._profiles.get(profile_name)
        if not config:
            raise KeyError(f"OCR 功能键 '{key}' 绑定的档案 '{profile_name}' 不存在")

        runtime_token = config.token or self._resolve_key(config.provider)
        current_hash = config.config_hash(runtime_token)

        cache_key = f"{key}:{profile_name}"
        if cache_key in self._instances and self._hashes.get(cache_key) == current_hash:
            return self._instances[cache_key]

        async with self._lock:
            if cache_key in self._instances and self._hashes.get(cache_key) == current_hash:
                return self._instances[cache_key]

            if len(self._instances) >= MAX_INSTANCES and cache_key not in self._instances:
                raise RuntimeError(f"OCR 实例数已达上限 ({MAX_INSTANCES})")

            provider_class = self._provider_registry.get(config.provider)
            if not provider_class:
                raise ValueError(f"未知的 OCR Provider: {config.provider}")

            # 将运行时 token 注入 config
            if not config.token and runtime_token:
                config = OCRConfig(
                    provider=config.provider,
                    mode=config.mode,
                    api_url=config.api_url,
                    token=runtime_token,
                    model=config.model,
                    use_chart_recognition=config.use_chart_recognition,
                    use_doc_orientation_classify=config.use_doc_orientation_classify,
                    use_doc_unwarping=config.use_doc_unwarping,
                    extra_params=config.extra_params,
                )

            provider = provider_class(config)
            self._instances[cache_key] = provider
            self._hashes[cache_key] = current_hash
            logger.info(f"已创建 OCR 实例: {key} -> {profile_name} ({config.provider}/{config.mode})")
            return provider

    def has_binding(self, function_key: str) -> bool:
        """检查是否有可用的 OCR 绑定"""
        key = function_key if isinstance(function_key, str) else function_key.value
        profile_name = self._bindings.get(key)
        return profile_name is not None and profile_name in self._profiles

    def reset(self) -> None:
        self._profiles.clear()
        self._bindings.clear()
        self._instances.clear()
        self._hashes.clear()


# 模块级单例
_ocr_manager: Optional[OCRManager] = None


def get_ocr_manager() -> OCRManager:
    global _ocr_manager
    if _ocr_manager is None:
        _ocr_manager = OCRManager()
    return _ocr_manager
