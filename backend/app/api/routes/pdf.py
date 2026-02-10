"""PDF 翻译 API 路由 — 瘦路由层，只做参数校验 + 委托给 translation_workflow

upload 接口为异步模式：立即返回 task_id，翻译在后台执行。
前端通过 SSE 端点跟踪进度，通过 /result/{task_id} 获取最终结果。

Requirements: 1.7
"""
import asyncio
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Form

from app.core.key_store import get_api_key
from app.services.task_manager import get_task_manager
from app.services.llm_setup import LLMSetupService
from app.services.pipelines.base import CancellationToken
from agent.workflows.translation_workflow import run_translation_workflow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pdf", tags=["pdf"])

# 存储已完成任务的翻译结果，供 /result/{task_id} 端点查询
_task_results: dict[str, dict] = {}


async def _run_workflow_background(
    task_id: str,
    file_content: bytes,
    filename: str,
    enable_ocr: bool,
    cancellation_token: CancellationToken,
) -> None:
    """后台执行翻译工作流，完成后将结果存入 _task_results。"""
    tm = get_task_manager()
    try:
        result = await run_translation_workflow(
            file_content=file_content,
            filename=filename,
            task_id=task_id,
            enable_ocr=enable_ocr,
            cancellation_token=cancellation_token,
        )
        _task_results[task_id] = result
        logger.info("✅ 后台翻译完成: task_id=%s", task_id)
    except asyncio.CancelledError:
        _task_results[task_id] = {"task_id": task_id, "error": "cancelled"}
        logger.info("🛑 后台翻译已取消: task_id=%s", task_id)
    except Exception as exc:
        _task_results[task_id] = {"task_id": task_id, "error": str(exc)}
        logger.exception("❌ 后台翻译失败: task_id=%s", task_id)
    finally:
        tm.finish_task(task_id)


@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    provider: str = Form("zhipuai"),
    model: str = Form("glm-4"),
    api_key: str | None = Form(None),
    system_prompt: str | None = Form(None),
    enable_ocr: bool = Form(False),
):
    """上传 PDF 并启动异步翻译，立即返回 task_id"""
    # 参数校验
    if not file.filename or not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")

    actual_key = get_api_key(provider, api_key)
    if not actual_key:
        raise HTTPException(status_code=400, detail=f"API key required for provider: {provider}")

    # 读取文件内容
    content = await file.read()
    logger.info(
        "📄 上传: %s | %.1f KB | LLM=%s/%s | OCR=%s",
        file.filename,
        len(content) / 1024,
        provider,
        model,
        "开" if enable_ocr else "关",
    )

    # 确保 LLM 已配置
    LLMSetupService.ensure_translation_ready(provider, model, actual_key)

    # 创建任务
    tm = get_task_manager()
    task_info = tm.create_task(file.filename)
    task_id = task_info.task_id

    # 创建取消令牌
    cancellation_token = CancellationToken()

    # 启动后台翻译工作流
    bg_task = asyncio.create_task(
        _run_workflow_background(
            task_id=task_id,
            file_content=content,
            filename=file.filename,
            enable_ocr=enable_ocr,
            cancellation_token=cancellation_token,
        )
    )
    task_info.asyncio_tasks.append(bg_task)

    return {"task_id": task_id, "status": "processing"}


@router.get("/result/{task_id}")
async def get_result(task_id: str):
    """获取已完成翻译任务的结果"""
    # 先检查结果缓存
    if task_id in _task_results:
        result = _task_results[task_id]
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
        # 剔除二进制字段（images/ocr_images），这些已保存到 TranslationStore，
        # 前端通过图片 URL 访问，不需要在 JSON 里返回
        safe_result = {
            k: v for k, v in result.items()
            if k not in ("images", "ocr_images")
        }
        return safe_result

    # 检查任务是否仍在运行
    tm = get_task_manager()
    task_info = tm.get_task(task_id)
    if task_info is not None:
        return {"task_id": task_id, "status": "processing"}

    raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")


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
