"""Pipeline 编排器 — 路由层唯一需要调用的入口

职责：
1. 配置 LLM（注册到 LLMManager）
2. 选择管线（LLM / OCR）
3. 管理异步任务（创建、取消、清理）
4. 保存翻译结果
"""
import asyncio
import logging
import time
from typing import Optional

from backend.app.services.task_manager import get_task_manager, TaskInfo
from backend.app.services.translation_store import get_translation_store
from backend.app.services.translator import TranslationService
from backend.app.services.llm_setup import LLMSetupService
from core.llm.config import FunctionKey
from core.llm.manager import get_llm_manager
from core.ocr.manager import get_ocr_manager
from .base import BasePipeline, PipelineResult, CancellationToken
from .llm_pipeline import LLMPipeline
from .ocr_pipeline import OCRPipeline

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """管线编排器"""

    async def process(
        self,
        file_content: bytes,
        filename: str,
        provider: str,
        model: str,
        api_key: str,
        enable_ocr: bool = False,
        system_prompt: Optional[str] = None,
    ) -> dict:
        """
        完整处理流程：配置 LLM → 选择管线 → 执行 → 保存结果 → 返回响应数据。

        Returns:
            dict: 可直接作为 API 响应返回的字典
        """
        # 1. 配置 LLM
        self._setup_llm(provider, model, api_key)

        # 2. 创建任务
        tm = get_task_manager()
        task_info = tm.create_task(filename)
        token = CancellationToken()

        logger.info(f"📄 处理: {filename} | LLM={provider}/{model} | OCR={'开' if enable_ocr else '关'} | task={task_info.task_id}")

        try:
            job_start = time.time()

            # 3. 选择并执行管线
            pipeline = self._select_pipeline(enable_ocr, system_prompt, token)
            pipeline_task = asyncio.create_task(pipeline.execute(file_content, filename))
            task_info.asyncio_tasks = [pipeline_task]

            try:
                result = await pipeline_task
            except asyncio.CancelledError:
                logger.info(f"🛑 任务已取消: {task_info.task_id}")
                return {"error": "cancelled", "task_id": task_info.task_id}

            total_time = time.time() - job_start
            logger.info(f"🎉 任务完成 | 总耗时 {total_time:.1f}s")

            # 4. 保存结果
            entry = await self._save_result(filename, result, provider, model, enable_ocr)

            # 5. 构建响应
            translator = await TranslationService.from_manager(FunctionKey.TRANSLATION)
            return self._build_response(task_info, entry, result, translator, model)

        except asyncio.CancelledError:
            return {"error": "cancelled", "task_id": task_info.task_id}
        finally:
            tm.finish_task(task_info.task_id)

    def _setup_llm(self, provider: str, model: str, api_key: str):
        """确保 translation binding 可用 — 不再创建临时 profile，而是复用用户配置的档案"""
        manager = get_llm_manager()
        # 如果用户已经通过 binding 配置了 translation，直接用
        bindings = manager.get_all_bindings()
        bound = bindings.get("translation")
        if bound and manager.get_profile(bound):
            return
        # 否则回退：用请求参数临时注册（兼容旧逻辑）
        LLMSetupService.ensure_translation_ready(provider, model, api_key)

    def _select_pipeline(
        self,
        enable_ocr: bool,
        system_prompt: Optional[str],
        token: CancellationToken,
    ) -> BasePipeline:
        """根据参数选择管线"""
        if enable_ocr:
            ocr_mgr = get_ocr_manager()
            if ocr_mgr.has_binding("ocr"):
                return OCRPipeline(system_prompt=system_prompt, token=token)
            else:
                logger.warning("⚠️  OCR 已启用但未绑定 Provider，回退到 LLM 管线")
        return LLMPipeline(system_prompt=system_prompt, token=token)

    async def _save_result(
        self,
        filename: str,
        result: PipelineResult,
        provider: str,
        model: str,
        enable_ocr: bool,
    ) -> dict:
        """保存翻译结果到 Translation/{id}/ 文件夹"""
        store = get_translation_store()
        profile = result.prompt_profile
        return await store.save(
            filename=filename,
            translated_md=result.translated_md,
            images=result.images,
            ocr_md=result.ocr_md,
            ocr_images=result.ocr_images,
            meta_extra={
                "provider": provider,
                "model": model,
                "enable_ocr": enable_ocr,
                "prompt_profile": {
                    "domain": profile.domain if profile else "",
                    "terminology_count": len(profile.terminology) if profile else 0,
                } if profile else None,
            },
        )

    @staticmethod
    def _build_response(
        task_info: TaskInfo,
        entry: dict,
        result: PipelineResult,
        translator: TranslationService,
        model: str,
    ) -> dict:
        """构建 API 响应"""
        profile = result.prompt_profile
        return {
            "task_id": task_info.task_id,
            "translation_id": entry["id"],
            "markdown": result.translated_md,
            "ocr_markdown": result.ocr_md,
            "provider_used": translator.get_provider_name(),
            "model_used": model,
            "prompt_profile": {
                "domain": profile.domain if profile else "",
                "terminology_count": len(profile.terminology) if profile else 0,
                "keep_english": profile.keep_english if profile else [],
                "generated_prompt": profile.translation_prompt if profile else "",
            } if profile else None,
        }
