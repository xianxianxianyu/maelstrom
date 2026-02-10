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

# ---------------------------------------------------------------------------
# Module-level singletons for QAAgent and its dependencies
# ---------------------------------------------------------------------------
_qa_agent = None
_doc_search_tool = None


def _get_doc_search_tool():
    """获取或创建 DocSearchTool 单例"""
    global _doc_search_tool
    if _doc_search_tool is None:
        from agent.tools.doc_search_tool import DocSearchTool
        _doc_search_tool = DocSearchTool()
    return _doc_search_tool


def _get_qa_agent():
    """获取或创建 QAAgent 单例（维护跨请求的对话历史）"""
    global _qa_agent
    if _qa_agent is None:
        from agent.agents.qa_agent import QAAgent
        _qa_agent = QAAgent(
            doc_search_tool=_get_doc_search_tool(),
            translation_service=None,  # 延迟初始化，由 QAAgent 内部处理
        )
    return _qa_agent


class QARequest(BaseModel):
    """QA 请求"""
    question: str
    context: Optional[str] = ""
    profile_name: Optional[str] = None
    session_id: Optional[str] = None
    doc_id: Optional[str] = None


class QAResponse(BaseModel):
    """QA 响应"""
    answer: str
    profile_used: str
    citations: list[dict] = []


@router.post("/qa", response_model=QAResponse)
async def qa_chat(request: QARequest):
    """问答接口 — 使用 QAAgent 进行 RAG 增强的问答

    支持 session_id 进行多轮对话，支持 doc_id 限定检索范围。
    向后兼容：session_id 和 doc_id 为可选参数。
    """
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
        # 使用 QAAgent 进行问答
        qa_agent = _get_qa_agent()

        # 构建 QAAgent 输入
        input_data = {"question": request.question}
        if request.session_id is not None:
            input_data["session_id"] = request.session_id
        if request.doc_id is not None:
            input_data["doc_id"] = request.doc_id

        result = await qa_agent.run(input_data)

        return QAResponse(
            answer=result.get("answer", ""),
            profile_used=profile_name,
            citations=result.get("citations", []),
        )
    except ValueError as e:
        logger.exception(f"QA 请求参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
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
                "description": "RAG Question-Answering Agent: answers questions using document retrieval and configured QA LLM, supports multi-turn conversation via session_id and document scoping via doc_id",
                "available": True,
            }
        ]
    }
