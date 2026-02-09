"""Agent API 路由 — QA 问答 + Agent 列表"""
import sys
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

# 确保 agent 包可导入
PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.llm.manager import get_llm_manager
from core.llm.config import FunctionKey, LLMConfig
from app.core.key_store import key_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])


class QARequest(BaseModel):
    """QA 请求"""
    question: str
    context: Optional[str] = ""
    profile_name: Optional[str] = None


class QAResponse(BaseModel):
    """QA 响应"""
    answer: str
    profile_used: str


@router.post("/qa", response_model=QAResponse)
async def qa_chat(request: QARequest):
    """问答接口 — 使用指定 LLM 档案回答问题"""
    manager = get_llm_manager()

    # 确定使用哪个 profile
    profile_name = request.profile_name
    if not profile_name:
        # 优先使用 qa binding，否则用 translation binding
        bindings = manager.get_all_bindings()
        profile_name = bindings.get(FunctionKey.QA.value) or bindings.get(FunctionKey.TRANSLATION.value)

    if not profile_name:
        raise HTTPException(status_code=400, detail="未配置 QA 档案，请先在 LLM 配置中设置")

    profile = manager.get_profile(profile_name)
    if not profile:
        raise HTTPException(status_code=400, detail=f"档案 '{profile_name}' 不存在")

    # 确保有 API Key
    runtime_key = profile.api_key or key_store.get_key(profile.provider)
    if not runtime_key:
        raise HTTPException(status_code=400, detail=f"Provider '{profile.provider}' 缺少 API Key")

    # 注册到 QA 功能键并获取实例
    config = LLMConfig(
        provider=profile.provider,
        model=profile.model,
        api_key=runtime_key,
        base_url=profile.base_url,
        temperature=profile.temperature,
        max_tokens=profile.max_tokens,
    )
    manager.register(FunctionKey.QA, config)

    try:
        instance = await manager.get(FunctionKey.QA)

        system_prompt = "You are a helpful assistant. Answer questions clearly and concisely in the same language as the question."
        if request.context:
            system_prompt += f"\n\nContext:\n{request.context}"

        answer = await instance.complete(request.question, system_prompt)

        return QAResponse(answer=answer, profile_used=profile_name)
    except Exception as e:
        logger.exception(f"QA 调用失败: {e}")
        raise HTTPException(status_code=500, detail=f"QA 调用失败: {str(e)}")


@router.get("/list")
async def list_agents():
    """列出可用的 Agent"""
    return {
        "agents": [
            {
                "name": "qa",
                "description": "Question-Answering Agent: answers questions using configured QA LLM",
                "available": True,
            }
        ]
    }
