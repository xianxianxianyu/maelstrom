"""Agent 注册表 — 管理所有可用 Agent"""
import logging
from typing import Dict, Optional, Type

from .base import BaseAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Agent 注册表，支持按名称注册和获取 Agent"""

    def __init__(self):
        self._agents: Dict[str, Type[BaseAgent]] = {}

    def register(self, agent_class: Type[BaseAgent]) -> Type[BaseAgent]:
        """注册 Agent 类（可作为装饰器使用）

        用法:
            registry = AgentRegistry()

            @registry.register
            class MyAgent(BaseAgent):
                ...
        """
        # 创建临时实例获取 name（因为 name 是 property）
        # 对于类级别注册，使用类名作为 key
        name = agent_class.__name__
        if name in self._agents:
            logger.warning(f"Agent '{name}' 已存在，将被覆盖")
        self._agents[name] = agent_class
        logger.info(f"已注册 Agent: {name}")
        return agent_class

    def get(self, name: str) -> Optional[Type[BaseAgent]]:
        """按名称获取 Agent 类"""
        return self._agents.get(name)

    def create(self, name: str, **kwargs) -> BaseAgent:
        """创建 Agent 实例"""
        agent_class = self._agents.get(name)
        if not agent_class:
            raise KeyError(f"Agent '{name}' 未注册")
        return agent_class(**kwargs)

    def list_agents(self) -> list[str]:
        """列出所有已注册的 Agent 名称"""
        return list(self._agents.keys())

    def list_agents_info(self) -> list[dict]:
        """列出所有 Agent 的详细信息"""
        result = []
        for name, cls in self._agents.items():
            instance = cls()
            result.append({
                "class_name": name,
                "name": instance.name,
                "description": instance.description,
            })
        return result


# 全局注册表
agent_registry = AgentRegistry()
