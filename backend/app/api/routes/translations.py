"""翻译历史 API — 列表/详情/删除/图片"""
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from app.services.translation_store import get_translation_store
from app.services.paper_repository_service import get_paper_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/translations", tags=["translations"])


@router.get("")
async def list_translations():
    """返回所有翻译记录（最新在前）"""
    store = get_translation_store()
    entries = await store.list_entries()

    task_ids = [str(entry.get("task_id")) for entry in entries if entry.get("task_id")]
    if task_ids:
        try:
            repo = await get_paper_repository()
            papers = await repo.get_many_by_ids(task_ids)

            for entry in entries:
                task_id = entry.get("task_id")
                if not task_id:
                    continue
                paper = papers.get(str(task_id))
                if not paper:
                    continue

                tags = paper.get("tags") if isinstance(paper.get("tags"), list) else []
                if not tags:
                    tags = []
                    domain = str(paper.get("domain") or "").strip()
                    if domain:
                        tags.append(domain)
                    for kw in paper.get("keywords", []) or []:
                        text = str(kw).strip()
                        if text and text not in tags:
                            tags.append(text)
                        if len(tags) >= 8:
                            break

                entry["paper_title"] = (
                    str(paper.get("title_zh") or "").strip()
                    or str(paper.get("title") or "").strip()
                    or entry.get("display_name")
                )
                entry["paper_keywords"] = paper.get("keywords", []) or []
                entry["paper_tags"] = tags
                entry["paper_domain"] = paper.get("domain")
                entry["paper_year"] = paper.get("year")
                entry["index_status"] = "indexed"
        except Exception as exc:
            logger.warning("Failed to enrich translation entries with paper data: %s", exc)

    return {"entries": entries}


@router.get("/{tid}")
async def get_translation(tid: str):
    """返回指定翻译的 markdown + meta"""
    store = get_translation_store()
    result = await store.get_entry(tid)
    if not result:
        raise HTTPException(status_code=404, detail=f"翻译记录 {tid} 不存在")
    return result


@router.delete("/{tid}")
async def delete_translation(tid: str):
    """删除指定翻译（文件夹 + 索引条目）"""
    store = get_translation_store()
    removed = await store.delete_entry(tid)
    if not removed:
        raise HTTPException(status_code=404, detail=f"翻译记录 {tid} 不存在")
    return {"message": f"翻译 {tid} 已删除"}


@router.get("/{tid}/images/{filename}")
async def get_translation_image(tid: str, filename: str):
    """返回翻译中的图片文件"""
    store = get_translation_store()
    path = store.get_image_path(tid, filename)
    if not path:
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(path)
