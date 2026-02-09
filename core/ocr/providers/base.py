"""OCR Provider 抽象基类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict


@dataclass
class OCRResult:
    """OCR 识别结果"""
    markdown: str  # 识别出的 markdown 文本
    images: Dict[str, bytes]  # 图片名 -> 图片字节数据


class BaseOCRProvider(ABC):
    """OCR Provider 抽象基类"""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    async def recognize(self, file_bytes: bytes, file_type: int = 0) -> OCRResult:
        """识别文件内容

        Args:
            file_bytes: 文件字节数据
            file_type: 0=PDF, 1=图片
        Returns:
            OCRResult 包含 markdown 文本和图片
        """
        pass
