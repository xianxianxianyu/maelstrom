"""BaseAgent 抽象基类 — 所有 Agent 的基础接口"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Agent 抽象基类

    所有 Agent 必须实现:
    - name: Agent 名称
    - description: Agent 描述
    - run(): 执行 Agent 主逻辑
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent 唯一标识名"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Agent 功能描述"""
        pass

    async def setup(self) -> None:
        """Agent 初始化（可选覆盖）"""
        logger.info(f"Agent '{self.name}' setup complete")

    async def teardown(self) -> None:
        """Agent 清理（可选覆盖）"""
        logger.info(f"Agent '{self.name}' teardown complete")

    @abstractmethod
    async def run(self, input_data: Any, **kwargs) -> Any:
        """执行 Agent 主逻辑

        Args:
            input_data: 输入数据（类型由子类定义）
            **kwargs: 额外参数

        Returns:
            Agent 执行结果
        """
        pass

    async def __call__(self, input_data: Any, **kwargs) -> Any:
        """便捷调用：自动执行 setup -> run -> teardown"""
        await self.setup()
        try:
            result = await self.run(input_data, **kwargs)
            return result
        finally:
            await self.teardown()
