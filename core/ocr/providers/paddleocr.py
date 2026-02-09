"""PaddleOCR Provider — 支持同步和异步两种模式"""
import asyncio
import base64
import json
import logging
from typing import Dict

import httpx

from .base import BaseOCRProvider, OCRResult
from ..config import OCRConfig

logger = logging.getLogger(__name__)

# 默认 API 地址
DEFAULT_SYNC_URL = "https://i8i44al2jfmfg1p3.aistudio-app.com/layout-parsing"
DEFAULT_ASYNC_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
DEFAULT_MODEL = "PaddleOCR-VL-1.5"

# 超时设置
SYNC_TIMEOUT = 600  # 同步模式 10 分钟（大 PDF 可能非常慢）
ASYNC_POLL_INTERVAL = 5  # 异步轮询间隔 5 秒
ASYNC_MAX_WAIT = 900  # 异步最大等待 900 秒（15 分钟，大 PDF 需要较长处理时间）


class PaddleOCRProvider(BaseOCRProvider):
    """PaddleOCR Provider，支持同步(layout-parsing)和异步(jobs)两种模式"""

    def __init__(self, config: OCRConfig):
        self._config = config
        self._mode = config.mode or "sync"
        self._token = config.token
        self._model = config.model or DEFAULT_MODEL
        if self._mode == "sync":
            self._api_url = config.api_url or DEFAULT_SYNC_URL
        else:
            self._api_url = config.api_url or DEFAULT_ASYNC_URL

    @property
    def provider_name(self) -> str:
        return "paddleocr"

    async def recognize(self, file_bytes: bytes, file_type: int = 0) -> OCRResult:
        if self._mode == "async":
            return await self._recognize_async(file_bytes, file_type)
        return await self._recognize_sync(file_bytes, file_type)

    async def _recognize_sync(self, file_bytes: bytes, file_type: int) -> OCRResult:
        """同步模式：直接 POST base64 编码的文件"""
        file_data = base64.b64encode(file_bytes).decode("ascii")
        headers = {
            "Authorization": f"token {self._token}",
            "Content-Type": "application/json",
        }
        payload = {
            "file": file_data,
            "fileType": file_type,
            "useDocOrientationClassify": self._config.use_doc_orientation_classify,
            "useDocUnwarping": self._config.use_doc_unwarping,
            "useChartRecognition": self._config.use_chart_recognition,
        }

        async with httpx.AsyncClient(timeout=SYNC_TIMEOUT) as client:
            resp = await client.post(self._api_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        return await self._parse_result(data.get("result", {}))

    async def _recognize_async(self, file_bytes: bytes, file_type: int) -> OCRResult:
        """异步模式：提交任务 → 轮询结果 → 解析 JSONL"""
        headers = {"Authorization": f"bearer {self._token}"}
        optional_payload = {
            "useDocOrientationClassify": self._config.use_doc_orientation_classify,
            "useDocUnwarping": self._config.use_doc_unwarping,
            "useChartRecognition": self._config.use_chart_recognition,
        }

        async with httpx.AsyncClient(timeout=SYNC_TIMEOUT) as client:
            # 提交任务
            data_fields = {
                "model": self._model,
                "optionalPayload": json.dumps(optional_payload),
            }
            files = {"file": ("document.pdf", file_bytes, "application/pdf")}
            resp = await client.post(
                self._api_url, headers=headers, data=data_fields, files=files
            )
            resp.raise_for_status()
            job_id = resp.json()["data"]["jobId"]
            logger.info(f"PaddleOCR 异步任务已提交: {job_id}")

            # 轮询结果
            elapsed = 0
            while elapsed < ASYNC_MAX_WAIT:
                await asyncio.sleep(ASYNC_POLL_INTERVAL)
                elapsed += ASYNC_POLL_INTERVAL

                poll_resp = await client.get(
                    f"{self._api_url}/{job_id}", headers=headers
                )
                poll_resp.raise_for_status()
                state = poll_resp.json()["data"]["state"]

                if state == "done":
                    jsonl_url = poll_resp.json()["data"]["resultUrl"]["jsonUrl"]
                    logger.info(f"PaddleOCR 任务完成: {job_id}")
                    return await self._fetch_jsonl_result(client, jsonl_url)
                elif state == "failed":
                    error_msg = poll_resp.json()["data"].get("errorMsg", "未知错误")
                    raise RuntimeError(f"PaddleOCR 任务失败: {error_msg}")
                else:
                    if elapsed % 30 == 0:  # 每 30 秒打一次 INFO 日志
                        logger.info(f"PaddleOCR 任务处理中: {job_id}, 已等待 {elapsed}s, 状态: {state}")
                    else:
                        logger.debug(f"PaddleOCR 任务状态: {state}, 已等待 {elapsed}s")

            raise TimeoutError(f"PaddleOCR 异步任务超时 ({ASYNC_MAX_WAIT}s)")

    async def _fetch_jsonl_result(self, client: httpx.AsyncClient, jsonl_url: str) -> OCRResult:
        """下载并解析 JSONL 结果"""
        resp = await client.get(jsonl_url)
        resp.raise_for_status()

        all_markdown = []
        all_images: Dict[str, bytes] = {}

        for line in resp.text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            result = json.loads(line).get("result", {})
            parsed = await self._parse_result(result)
            all_markdown.append(parsed.markdown)
            all_images.update(parsed.images)

        return OCRResult(
            markdown="\n\n".join(all_markdown),
            images=all_images,
        )

    async def _parse_result(self, result: dict) -> OCRResult:
        """解析 PaddleOCR 返回的 layoutParsingResults"""
        all_markdown = []
        all_images: Dict[str, bytes] = {}

        for res in result.get("layoutParsingResults", []):
            md_data = res.get("markdown", {})
            md_text = md_data.get("text", "")
            all_markdown.append(md_text)

            # 下载图片并转为字节数据
            for img_path, img_url in md_data.get("images", {}).items():
                img_bytes = await self._download_image(img_url)
                if img_bytes:
                    all_images[img_path] = img_bytes

        return OCRResult(
            markdown="\n\n".join(all_markdown),
            images=all_images,
        )

    async def _download_image(self, url: str) -> bytes:
        """下载图片 URL 并返回字节数据"""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.content
        except Exception as e:
            logger.warning(f"下载 OCR 图片失败: {url}, 错误: {e}")
            return b""
