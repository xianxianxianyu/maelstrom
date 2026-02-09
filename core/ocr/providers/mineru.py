"""MineRU Provider — MineRU cloud API for PDF/image extraction to Markdown

Batch upload flow (for local files):
1. POST /api/v4/file-urls/batch -> get batch_id + presigned upload URLs
2. PUT  presigned URL           -> upload file (no Content-Type needed)
3. System auto-submits extract task after upload
4. GET  /api/v4/extract-results/batch/{batch_id} -> poll results
5. Download full_zip_url -> extract markdown + images from zip
"""
import asyncio
import io
import logging
import uuid
import zipfile
from typing import Dict

import httpx

from .base import BaseOCRProvider, OCRResult
from ..config import OCRConfig

logger = logging.getLogger(__name__)

BASE_URL = "https://mineru.net/api/v4"
TIMEOUT = 120
POLL_INTERVAL = 5
MAX_WAIT = 600


class MineRUProvider(BaseOCRProvider):

    def __init__(self, config: OCRConfig):
        self._config = config
        self._token = config.token
        self._model_version = config.model or "vlm"

    @property
    def provider_name(self) -> str:
        return "mineru"

    def _auth_headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
        }

    async def recognize(self, file_bytes: bytes, file_type: int = 0) -> OCRResult:
        ext = "pdf" if file_type == 0 else "png"
        filename = f"upload_{uuid.uuid4().hex[:8]}.{ext}"

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # Step 1: get presigned upload URLs
            url = f"{BASE_URL}/file-urls/batch"
            payload = {
                "files": [{"name": filename}],
                "model_version": self._model_version,
                "enable_formula": True,
                "enable_table": True,
            }
            logger.info(f"MineRU Step1: POST {url} | file={filename} model={self._model_version}")
            logger.info(f"MineRU token prefix: {self._token[:8]}..." if self._token else "MineRU token: EMPTY!")
            resp = await client.post(
                url,
                headers=self._auth_headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(
                    f"MineRU get upload URL failed: {data.get('msg', data)}"
                )

            batch_id = data["data"]["batch_id"]
            file_urls = data["data"]["file_urls"]
            if not file_urls:
                raise RuntimeError("MineRU returned empty file_urls")

            presigned_url = file_urls[0]
            logger.info(f"MineRU batch_id={batch_id}, uploading {filename}")

            # Step 2: upload file via PUT to presigned URL (no Content-Type needed)
            put_resp = await client.put(
                presigned_url,
                content=file_bytes,
            )
            put_resp.raise_for_status()
            logger.info(f"MineRU file uploaded: {filename}")

            # Step 3: system auto-submits task after upload, just poll results
            return await self._poll_batch(client, batch_id)

    async def _poll_batch(self, client: httpx.AsyncClient, batch_id: str) -> OCRResult:
        """Poll GET /api/v4/extract-results/batch/{batch_id} until done."""
        elapsed = 0
        while elapsed < MAX_WAIT:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

            resp = await client.get(
                f"{BASE_URL}/extract-results/batch/{batch_id}",
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                raise RuntimeError(f"MineRU poll failed: {data.get('msg', data)}")

            results = data.get("data", {}).get("extract_result", [])
            if not results:
                logger.debug(f"MineRU polling... {elapsed}s (no results yet)")
                continue

            item = results[0]
            state = item.get("state", "")

            if state == "done":
                zip_url = item.get("full_zip_url", "")
                logger.info(f"MineRU task done after {elapsed}s")
                if zip_url:
                    return await self._download_and_parse_zip(client, zip_url)
                else:
                    raise RuntimeError("MineRU task done but no full_zip_url")

            elif state == "failed":
                err = item.get("err_msg", "unknown error")
                raise RuntimeError(f"MineRU task failed: {err}")

            elif state in ("waiting-file", "pending", "running", "converting"):
                progress = item.get("extract_progress", {})
                pages = progress.get("extracted_pages", "?")
                total = progress.get("total_pages", "?")
                logger.info(f"MineRU state={state} ({pages}/{total} pages), {elapsed}s")
            else:
                logger.debug(f"MineRU state={state}, {elapsed}s")

        raise TimeoutError(f"MineRU timeout ({MAX_WAIT}s)")

    async def _download_and_parse_zip(
        self, client: httpx.AsyncClient, zip_url: str
    ) -> OCRResult:
        """Download the result zip and extract markdown + images."""
        resp = await client.get(zip_url)
        resp.raise_for_status()

        all_md = []
        all_images: Dict[str, bytes] = {}

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            for name in zf.namelist():
                lower = name.lower()
                if lower.endswith(".md"):
                    all_md.append(zf.read(name).decode("utf-8", errors="replace"))
                elif any(lower.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".svg")):
                    all_images[name] = zf.read(name)

        markdown = "\n\n".join(all_md) if all_md else "(MineRU zip contained no markdown)"
        logger.info(
            f"MineRU zip parsed: {len(all_md)} md files, {len(all_images)} images"
        )
        return OCRResult(markdown=markdown, images=all_images)
