"""翻译结果存储管理 — 文件夹结构 + index.json 索引"""
import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles

from app.services.image_utils import extract_base64_images

logger = logging.getLogger(__name__)

# 项目根目录 (core 同级)
# translation_store.py 位于 test/backend/app/services/
# parents: [0]=services [1]=app [2]=backend [3]=test
PROJECT_ROOT = Path(__file__).resolve().parents[3]
TRANSLATION_DIR = PROJECT_ROOT / "Translation"


class TranslationStore:
    """管理 Translation/{id}/ 文件夹结构和 index.json"""

    _lock = asyncio.Lock()

    # ── 公开方法 ──

    async def save(
        self,
        filename: str,
        translated_md: str,
        images: dict[str, bytes] | None = None,
        ocr_md: str | None = None,
        ocr_images: dict[str, bytes] | None = None,
        meta_extra: dict[str, Any] | None = None,
    ) -> dict:
        """
        保存一次翻译结果，返回 index entry。

        - translated_md: 翻译后 markdown（可能含 base64 或已用相对路径）
        - images: LLM 管线产生的图片 {name: bytes}
        - ocr_md: OCR 原始 markdown（可能含 base64 或相对路径）
        - ocr_images: OCR 管线产生的图片 {name: bytes}
        - meta_extra: 额外元数据 (provider, model, enable_ocr, prompt_profile 等)
        """
        tid = uuid.uuid4().hex[:8]
        folder = TRANSLATION_DIR / tid
        img_dir = folder / "images"
        img_dir.mkdir(parents=True, exist_ok=True)

        all_images: dict[str, bytes] = {}

        # 合并图片来源
        if images:
            all_images.update(images)
        if ocr_images:
            all_images.update(ocr_images)

        # 提取 translated_md 中的 base64 图片
        translated_md, b64_imgs = self._extract_base64_images(translated_md)
        all_images.update(b64_imgs)

        # 提取 ocr_md 中的 base64 图片
        if ocr_md:
            ocr_md, ocr_b64_imgs = self._extract_base64_images(ocr_md)
            all_images.update(ocr_b64_imgs)

        # 写入图片文件
        for name, data in all_images.items():
            async with aiofiles.open(img_dir / name, "wb") as f:
                await f.write(data)

        # 写入 markdown
        async with aiofiles.open(folder / "translated.md", "w", encoding="utf-8") as f:
            await f.write(translated_md)

        if ocr_md:
            async with aiofiles.open(folder / "ocr_raw.md", "w", encoding="utf-8") as f:
                await f.write(ocr_md)

        # 生成 display_name
        stem = Path(filename).stem
        index_data = await self._read_index()
        existing_names = [e["display_name"] for e in index_data.get("entries", [])]
        display_name = self._generate_display_name(stem, existing_names)

        # 构建 entry
        entry = {
            "id": tid,
            "filename": filename,
            "display_name": display_name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "has_ocr": ocr_md is not None,
            **(meta_extra or {}),
        }

        # 写入 meta.json
        async with aiofiles.open(folder / "meta.json", "w", encoding="utf-8") as f:
            await f.write(json.dumps(entry, ensure_ascii=False, indent=2))

        # 如果 meta_extra 包含 quality_report，单独保存为 quality_report.json
        if meta_extra and "quality_report" in meta_extra:
            qr_path = folder / "quality_report.json"
            async with aiofiles.open(qr_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(meta_extra["quality_report"], ensure_ascii=False, indent=2))

        # 更新 index.json
        await self._update_index(lambda d: d["entries"].insert(0, entry))

        logger.info(f"💾 翻译已保存: {folder} | display={display_name}")
        return entry

    async def list_entries(self) -> list[dict]:
        """返回所有翻译记录（最新在前）"""
        data = await self._read_index()
        return data.get("entries", [])

    async def get_entry(self, tid: str) -> dict | None:
        """返回指定翻译的 markdown + meta + quality_report"""
        folder = TRANSLATION_DIR / tid
        if not folder.is_dir():
            return None

        result: dict[str, Any] = {}

        md_path = folder / "translated.md"
        if md_path.exists():
            async with aiofiles.open(md_path, "r", encoding="utf-8") as f:
                result["markdown"] = await f.read()

        ocr_path = folder / "ocr_raw.md"
        if ocr_path.exists():
            async with aiofiles.open(ocr_path, "r", encoding="utf-8") as f:
                result["ocr_markdown"] = await f.read()

        meta_path = folder / "meta.json"
        if meta_path.exists():
            async with aiofiles.open(meta_path, "r", encoding="utf-8") as f:
                result["meta"] = json.loads(await f.read())

        qr_path = folder / "quality_report.json"
        if qr_path.exists():
            async with aiofiles.open(qr_path, "r", encoding="utf-8") as f:
                result["quality_report"] = json.loads(await f.read())

        return result if result else None

    async def delete_entry(self, tid: str) -> bool:
        """删除翻译记录（文件夹 + 索引条目）"""
        folder = TRANSLATION_DIR / tid
        if folder.is_dir():
            import shutil
            shutil.rmtree(folder)

        removed = False
        async def _remove(data):
            nonlocal removed
            before = len(data["entries"])
            data["entries"] = [e for e in data["entries"] if e["id"] != tid]
            removed = before > len(data["entries"])

        await self._update_index(_remove)
        if removed:
            logger.info(f"🗑️ 翻译已删除: {tid}")
        return removed

    def get_image_path(self, tid: str, image_name: str) -> Path | None:
        """返回图片文件路径"""
        p = TRANSLATION_DIR / tid / "images" / image_name
        return p if p.is_file() else None

    # ── 内部方法 ──

    def _extract_base64_images(self, markdown: str) -> tuple[str, dict[str, bytes]]:
        """从 markdown 中提取 base64 图片，替换为相对路径（委托给 image_utils）"""
        return extract_base64_images(markdown)

    @staticmethod
    def _generate_display_name(stem: str, existing: list[str]) -> str:
        """重名自动加后缀: paper, paper-2, paper-3, ..."""
        if stem not in existing:
            return stem
        n = 2
        while f"{stem}-{n}" in existing:
            n += 1
        return f"{stem}-{n}"

    async def _read_index(self) -> dict:
        """读取 index.json"""
        TRANSLATION_DIR.mkdir(parents=True, exist_ok=True)
        idx_path = TRANSLATION_DIR / "index.json"
        if not idx_path.exists():
            return {"entries": []}
        try:
            async with aiofiles.open(idx_path, "r", encoding="utf-8") as f:
                return json.loads(await f.read())
        except (json.JSONDecodeError, IOError):
            return {"entries": []}

    async def _update_index(self, updater) -> None:
        """带锁更新 index.json"""
        async with self._lock:
            data = await self._read_index()
            updater(data)
            TRANSLATION_DIR.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(
                TRANSLATION_DIR / "index.json", "w", encoding="utf-8"
            ) as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))


# 单例
_store: TranslationStore | None = None

def get_translation_store() -> TranslationStore:
    global _store
    if _store is None:
        _store = TranslationStore()
    return _store
