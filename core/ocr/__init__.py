"""OCR Multiton 管理模块

按档案(profile) + 绑定(binding) 管理 OCR 实例。

用法:
    from core.ocr import get_ocr_manager, OCRConfig

    manager = get_ocr_manager()
    manager.register_profile("paddle-sync", OCRConfig(provider="paddleocr", mode="sync", token="..."))
    manager.bind("ocr", "paddle-sync")
    provider = await manager.get("ocr")
    result = await provider.recognize(file_bytes)
"""
from .config import OCRConfig, OCRFunctionKey
from .manager import OCRManager, get_ocr_manager
from .loader import load_ocr_config_data, save_ocr_config_data

__all__ = [
    "OCRConfig",
    "OCRFunctionKey",
    "OCRManager",
    "get_ocr_manager",
    "load_ocr_config_data",
    "save_ocr_config_data",
]
