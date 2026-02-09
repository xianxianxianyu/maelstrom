"""示例 QA Agent — 基于 LLMManager 的问答 Agent"""
import sys
import logging
from pathlib import Path
from typing import Any

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.base import BaseAgent
from agent.registry import agent_registry
from core.llm import get_llm_manager, load_llm_configs, FunctionKey

logger = logging.getLogger(__name__)


@agent_registry.register
class QAAgent(BaseAgent):
    """问答 Agent：接收问题，使用 QA 功能键对应的 LLM 生成回答"""

    @property
    def name(self) -> str:
        return "qa"

    @property
    def description(self) -> str:
        return "Question-Answering Agent: answers questions using configured QA LLM"

    async def setup(self) -> None:
        """初始化：确保 LLMManager 已加载 QA 配置"""
        manager = get_llm_manager()
        if FunctionKey.QA.value not in manager.list_functions():
            configs = load_llm_configs()
            for key_str, config in configs.items():
                try:
                    fk = FunctionKey(key_str)
                    manager.register(fk, config)
                except ValueError:
                    pass
        await super().setup()

    async def run(self, input_data: Any, **kwargs) -> str:
        """执行问答

        Args:
            input_data: 问题字符串或 {"question": "...", "context": "..."} 字典
        """
        if isinstance(input_data, str):
            question = input_data
            context = ""
        elif isinstance(input_data, dict):
            question = input_data.get("question", "")
            context = input_data.get("context", "")
        else:
            raise ValueError(f"不支持的输入类型: {type(input_data)}")

        manager = get_llm_manager()
        instance = await manager.get(FunctionKey.QA)

        system_prompt = "You are a helpful assistant. Answer questions clearly and concisely."
        if context:
            system_prompt += f"\n\nContext:\n{context}"

        answer = await instance.complete(question, system_prompt)
        return answer
