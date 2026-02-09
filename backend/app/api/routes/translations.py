"""翻译历史 API — 列表/详情/删除/图片"""
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from app.services.translation_store import get_translation_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/translations", tags=["translations"])


@router.get("")
async def list_translations():
    """返回所有翻译记录（最新在前）"""
    store = get_translation_store()
    entries = await store.list_entries()
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
