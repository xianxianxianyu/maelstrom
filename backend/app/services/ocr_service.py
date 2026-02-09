"""OCR 服务封装 — 调用 OCRManager 获取 Provider 并执行识别"""
import logging
from pathlib import PurePosixPath

from core.ocr import get_ocr_manager, OCRFunctionKey
from core.ocr.providers.base import OCRResult

logger = logging.getLogger(__name__)


class OCRService:
    """OCR 服务，封装 Provider 调用和结果格式化"""

    def __init__(self, provider):
        self._provider = provider

    @classmethod
    async def from_manager(cls, function_key=None) -> "OCRService":
        """从 OCRManager 创建 OCRService"""
        key = function_key or OCRFunctionKey.OCR
        provider = await get_ocr_manager().get(key)
        return cls(provider)

    async def recognize(self, file_bytes: bytes, file_type: int = 0) -> tuple[str, dict[str, bytes]]:
        """
        识别文件，返回 (markdown, images_dict)。
        图片使用 ./images/fig_N.ext 相对路径，bytes 存入字典。
        """
        result = await self._provider.recognize(file_bytes, file_type)
        return self._rewrite_images(result)

    def _rewrite_images(self, result: OCRResult) -> tuple[str, dict[str, bytes]]:
        """将 OCR 图片重命名为 fig_N.ext，markdown 中路径改为 ./images/fig_N.ext"""
        markdown = result.markdown
        images: dict[str, bytes] = {}
        counter = 0

        for orig_path, img_bytes in result.images.items():
            if not img_bytes:
                continue
            counter += 1
            ext = PurePosixPath(orig_path).suffix.lstrip(".") or "png"
            if ext == "jpeg":
                ext = "jpg"
            new_name = f"fig_{counter}.{ext}"
            images[new_name] = img_bytes
            markdown = markdown.replace(orig_path, f"./images/{new_name}")

        return markdown, images

    def get_provider_name(self) -> str:
        return self._provider.provider_name
