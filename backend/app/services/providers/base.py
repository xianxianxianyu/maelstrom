from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ProviderConfig:
    """Configuration for a translation provider"""
    api_key: str
    model: str
    base_url: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.3


@dataclass
class ModelInfo:
    """Information about an available model"""
    id: str
    name: str
    provider: str
    description: str


class BaseProvider(ABC):
    """Abstract base for all translation providers"""

    def __init__(self, config: ProviderConfig):
        self.config = config

    @abstractmethod
    async def translate(self, text: str, system_prompt: str) -> str:
        """Translate text and return result"""
        pass

    @abstractmethod
    def get_available_models(self) -> list[ModelInfo]:
        """Return list of available models for this provider"""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier"""
        pass
