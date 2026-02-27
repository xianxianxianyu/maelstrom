"""翻译工作流入口 — 替代 PipelineOrchestrator.process()

创建 AgentContext，调用 OrchestratorAgent，返回兼容现有 API 响应格式的结果字典。
这是 API 层与 Agent 层之间的胶水代码。

Requirements: 5.1
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from agent.context import AgentContext
from agent.event_bus import get_event_bus
from agent.registry import agent_registry
from backend.app.services.pipelines.base import CancellationToken

# 显式导入所有 Agent 模块，触发 @agent_registry.register 装饰器
import agent.agents.orchestrator_agent  # noqa: F401
import agent.agents.terminology_agent   # noqa: F401
import agent.agents.ocr_agent           # noqa: F401
import agent.agents.translation_agent   # noqa: F401
import agent.agents.review_agent        # noqa: F401
import agent.agents.index_agent         # noqa: F401

logger = logging.getLogger(__name__)


async def run_translation_workflow(
    file_content: bytes,
    filename: str,
    task_id: str | None = None,
    enable_ocr: bool = False,
    cancellation_token: CancellationToken | None = None,
    orchestrator_agent: Any | None = None,
) -> dict:
    """翻译工作流入口 — 替代 PipelineOrchestrator.process()

    创建 AgentContext，获取全局 EventBus，创建并运行 OrchestratorAgent，
    返回包含翻译结果的字典。

    Args:
        file_content: PDF 文件字节内容
        filename: 文件名
        task_id: 可选的任务 ID（如果不提供则自动生成）
        cancellation_token: 可选的取消令牌
        orchestrator_agent: 可选的 OrchestratorAgent 实例（依赖注入，用于测试）

    Returns:
        dict: 包含 task_id, translated_md, quality_report 等

    Raises:
        Exception: OrchestratorAgent 执行失败时向上传播
    """
    # 1. 生成 task_id（如果未提供）
    if task_id is None:
        task_id = uuid.uuid4().hex[:8]

    # 2. 获取全局 EventBus
    event_bus = get_event_bus()

    # 3. 创建 CancellationToken（如果未提供）
    if cancellation_token is None:
        cancellation_token = CancellationToken()

    # 4. 创建 AgentContext
    ctx = AgentContext(
        task_id=task_id,
        filename=filename,
        file_content=file_content,
        event_bus=event_bus,
        enable_ocr=enable_ocr,
        cancellation_token=cancellation_token,
    )

    # 5. 获取或创建 OrchestratorAgent
    if orchestrator_agent is None:
        orchestrator_agent = agent_registry.create("OrchestratorAgent")

    # 6. 运行 OrchestratorAgent
    logger.info("Starting translation workflow: task_id=%s, filename=%s", task_id, filename)
    ctx = await orchestrator_agent(ctx)
    logger.info("Translation workflow complete: task_id=%s", task_id)

    # 7. 构建结果字典（兼容旧 API 响应格式）
    result: dict[str, Any] = {
        "task_id": ctx.task_id,
        "translation_id": ctx.translation_id,
        "markdown": ctx.translated_md,
        "translated_md": ctx.translated_md,
        "ocr_markdown": ctx.ocr_md,
        "images": ctx.images,
        "ocr_images": ctx.ocr_images,
        "quality_report": ctx.quality_report.to_dict() if ctx.quality_report else None,
        "glossary": ctx.glossary,
        "prompt_profile": {
            "domain": ctx.prompt_profile.domain if ctx.prompt_profile else "",
            "terminology_count": len(ctx.prompt_profile.terminology) if ctx.prompt_profile else 0,
            "keep_english": ctx.prompt_profile.keep_english if ctx.prompt_profile else [],
            "generated_prompt": ctx.prompt_profile.translation_prompt if ctx.prompt_profile else "",
        } if ctx.prompt_profile else None,
    }

    return result
