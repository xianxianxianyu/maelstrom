"""Pipeline 基类 — 定义翻译管线的统一接口和取消机制"""
import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from app.services.prompt_generator import PromptProfile

logger = logging.getLogger(__name__)


class CancellationToken:
    """轻量取消令牌，供 Pipeline 内部检查"""

    def __init__(self):
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def check(self):
        """如果已取消则抛出 CancelledError"""
        if self._cancelled:
            raise asyncio.CancelledError("任务已被用户取消")


@dataclass
class PipelineResult:
    """管线统一输出"""
    translated_md: str
    images: dict[str, bytes] = field(default_factory=dict)
    ocr_md: Optional[str] = None
    ocr_images: dict[str, bytes] = field(default_factory=dict)
    prompt_profile: Optional[PromptProfile] = None


class BasePipeline(ABC):
    """翻译管线抽象基类

    子类只需实现 execute()，公共逻辑（并发翻译、后处理）在基类提供。
    """

    # 并发翻译的最大并行数
    CONCURRENCY = 5

    def __init__(self, system_prompt: Optional[str] = None, token: Optional[CancellationToken] = None):
        self.system_prompt = system_prompt
        self.token = token or CancellationToken()

    @abstractmethod
    async def execute(self, file_content: bytes, filename: str) -> PipelineResult:
        """执行管线，返回统一结果"""
        pass
