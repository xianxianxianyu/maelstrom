"""LLM 配置数据类和功能键枚举"""
from dataclasses import dataclass, field
from enum import Enum
from hashlib import md5
from typing import Optional

from core.providers.base import ProviderConfig


class FunctionKey(str, Enum):
    """LLM 功能键枚举，每个功能对应一个独立的 LLM 实例"""
    TRANSLATION = "translation"
    QA = "qa"
    SUMMARIZATION = "summarization"
    DATABASE = "database"


@dataclass(frozen=True)
class LLMConfig:
    """LLM 实例配置"""
    provider: str  # "openai" | "deepseek" | "zhipuai"
    model: str  # "gpt-4o" | "deepseek-chat" | "glm-4"
    api_key: str = ""  # 空则运行时从 KeyStore 获取
    base_url: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.3
    extra_params: dict = field(default_factory=dict)

    def to_provider_config(self, runtime_api_key: str = "") -> ProviderConfig:
        """转换为现有 ProviderConfig，兼容现有 Provider 体系"""
        return ProviderConfig(
            api_key=self.api_key or runtime_api_key,
            model=self.model,
            base_url=self.base_url,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

    def config_hash(self, runtime_api_key: str = "") -> str:
        """生成配置哈希，用于检测配置变更"""
        key = self.api_key or runtime_api_key
        raw = f"{self.provider}|{self.model}|{key}|{self.base_url}|{self.max_tokens}|{self.temperature}"
        return md5(raw.encode()).hexdigest()
