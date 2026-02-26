"""QA系统统一LLM服务

封装QA系统中统一的LLM调用逻辑，避免各Agent重复导入LLM manager。
采用单例模式，确保LLM实例只初始化一次。
"""

import logging
from typing import List, Dict, Optional

from core.llm.manager import get_llm_manager
from core.llm.config import FunctionKey

logger = logging.getLogger(__name__)


class QALLMService:
    """QA系统统一LLM服务封装

    使用单例模式，确保整个QA Pipeline共享同一个LLM实例。
    """

    _instance: Optional["QALLMService"] = None

    def __init__(self):
        self._llm = None
        self._initialized = False

    @classmethod
    async def get_instance(cls) -> "QALLMService":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
            await cls._instance._init()
        return cls._instance

    async def _init(self) -> None:
        """初始化LLM实例"""
        if self._initialized:
            return

        try:
            llm_mgr = get_llm_manager()
            # 使用翻译功能的LLM配置
            self._llm = await llm_mgr.get(FunctionKey.TRANSLATION)
            self._initialized = True
            logger.info("QALLMService 初始化成功")
        except Exception as e:
            logger.warning(f"QALLMService LLM初始化失败: {e}")
            self._initialized = True  # 标记已尝试初始化，避免重试

    async def chat(self, system: str, user: str) -> str:
        """简单对话（单轮）

        Args:
            system: system prompt
            user: user prompt

        Returns:
            LLM回复内容
        """
        if not self._llm:
            await self._init()

        if not self._llm:
            logger.warning("LLM未初始化，无法生成回答")
            return ""

        try:
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ]
            result = await self._llm.chat(messages)
            return result.strip() if result else ""
        except Exception as e:
            logger.error(f"LLM chat调用失败: {e}")
            return ""

    async def chat_with_messages(self, messages: List[Dict[str, str]]) -> str:
        """多轮对话

        Args:
            messages: 消息列表 [{"role": "system/user", "content": "..."}]

        Returns:
            LLM回复内容
        """
        if not self._llm:
            await self._init()

        if not self._llm:
            return ""

        try:
            result = await self._llm.chat(messages)
            return result.strip() if result else ""
        except Exception as e:
            logger.error(f"LLM chat调用失败: {e}")
            return ""

    @property
    def is_available(self) -> bool:
        """检查LLM是否可用"""
        return self._llm is not None


# ========== 便捷函数 ==========

_qa_llm_service: Optional[QALLMService] = None


async def get_qa_llm() -> QALLMService:
    """获取QA LLM服务实例（便捷函数）"""
    global _qa_llm_service
    if _qa_llm_service is None:
        _qa_llm_service = await QALLMService.get_instance()
    return _qa_llm_service