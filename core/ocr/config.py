"""OCR 配置数据类和功能键枚举"""
from dataclasses import dataclass, field
from enum import Enum
from hashlib import md5
from typing import Optional


class OCRFunctionKey(str, Enum):
    """OCR 功能键枚举"""
    OCR = "ocr"


@dataclass(frozen=True)
class OCRConfig:
    """OCR 实例配置"""
    provider: str  # "paddleocr" | "mineru"
    mode: str = "sync"  # "sync" | "async"
    api_url: str = ""
    token: str = ""  # 空则运行时从 KeyStore 获取
    model: str = ""  # 异步模式使用的模型名
    use_chart_recognition: bool = False
    use_doc_orientation_classify: bool = False
    use_doc_unwarping: bool = False
    extra_params: dict = field(default_factory=dict)

    def config_hash(self, runtime_token: str = "") -> str:
        """生成配置哈希，用于检测配置变更"""
        tk = self.token or runtime_token
        raw = f"{self.provider}|{self.mode}|{self.api_url}|{tk}|{self.model}"
        return md5(raw.encode()).hexdigest()
