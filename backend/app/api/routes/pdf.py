"""PDF 翻译 API 路由 — 瘦路由层，只做参数校验 + 委托给 Orchestrator"""
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Form

from app.core.key_store import get_api_key
from app.services.task_manager import get_task_manager
from app.services.pipelines import PipelineOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pdf", tags=["pdf"])


@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    provider: str = Form("zhipuai"),
    model: str = Form("glm-4"),
    api_key: str | None = Form(None),
    system_prompt: str | None = Form(None),
    enable_ocr: bool = Form(False),
):
    """上传 PDF 并翻译"""
    # 参数校验
    if not file.filename or not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")

    actual_key = get_api_key(provider, api_key)
    if not actual_key:
        raise HTTPException(status_code=400, detail=f"API key required for provider: {provider}")

    # 读取文件内容
    content = await file.read()
    logger.info(f"📄 上传: {file.filename} | {len(content) / 1024:.1f} KB | LLM={provider}/{model} | OCR={'开' if enable_ocr else '关'}")

    # 委托给 Orchestrator
    orchestrator = PipelineOrchestrator()
    result = await orchestrator.process(
        file_content=content,
        filename=file.filename,
        provider=provider,
        model=model,
        api_key=actual_key,
        enable_ocr=enable_ocr,
        system_prompt=system_prompt,
    )

    # 处理取消情况
    if result.get("error") == "cancelled":
        raise HTTPException(status_code=499, detail="任务已取消")

    return result


@router.post("/cancel/{task_id}")
async def cancel_task(task_id: str):
    """取消正在运行的翻译任务"""
    tm = get_task_manager()
    if tm.cancel_task(task_id):
        return {"message": f"任务 {task_id} 已取消"}
    raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在或已完成")


@router.post("/cancel-all")
async def cancel_all_tasks():
    """取消所有运行中的任务"""
    tm = get_task_manager()
    tm.cancel_all()
    return {"message": "所有任务已取消"}


@router.get("/tasks")
async def list_tasks():
    """列出当前运行中的任务"""
    tm = get_task_manager()
    return {"tasks": tm.list_tasks()}
