"""质量报告 API 路由 — 获取翻译的质量报告

提供以下端点：
- GET /api/translations/{id}/quality  获取翻译的质量报告

从 TranslationStore 中读取已保存的 quality_report 元数据。

Requirements: 6.2, 7.4
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.services.translation_store import get_translation_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/translations", tags=["quality"])


@router.get("/{translation_id}/quality")
async def get_quality_report(translation_id: str):
    """获取翻译的质量报告

    从 TranslationStore 加载指定翻译条目，提取其中的 quality_report。
    quality_report 在翻译完成时由 OrchestratorAgent 保存到 meta_extra 中。

    Args:
        translation_id: 翻译记录的唯一标识

    Returns:
        质量报告字典，包含 score、terminology_issues、format_issues、
        untranslated、suggestions、timestamp 等字段

    Raises:
        HTTPException 404: 翻译记录不存在
        HTTPException 404: 该翻译没有质量报告
    """
    store = get_translation_store()

    # 加载翻译条目
    entry = await store.get_entry(translation_id)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"Translation '{translation_id}' not found",
        )

    # 从 meta 中提取 quality_report
    meta = entry.get("meta") or {}
    quality_report = meta.get("quality_report")

    if quality_report is None:
        raise HTTPException(
            status_code=404,
            detail=f"Quality report not available for translation '{translation_id}'",
        )

    logger.info("📊 获取质量报告: id=%s, score=%s", translation_id, quality_report.get("score"))
    return quality_report
