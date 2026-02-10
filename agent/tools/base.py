"""BaseTool ABC 和 ToolResult 数据类 — Agent 工具系统的基础接口

提供标准化的工具接口（BaseTool ABC），包含 name、description 和 execute 方法。
工具执行结果通过 ToolResult 返回，包含结构化的错误信息和可恢复性标识。

Requirements: 5.2, 5.4
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """工具执行结果

    所有 Tool 的 execute() 方法返回此数据类，提供统一的结果格式。

    Attributes:
        success: 执行是否成功
        data: 成功时的返回数据（任意类型）
        error: 失败时的错误信息（空字符串表示无错误）
        recoverable: 失败时是否可恢复（可重试）
            - True: 可重试错误（网络超时、API 限流等）
            - False: 不可恢复错误（配置缺失、文件损坏等）
    """

    success: bool
    data: Any = None
    error: str = ""
    recoverable: bool = True


class BaseTool(ABC):
    """Agent 工具抽象基类

    所有 Tool 必须实现:
    - name: 工具唯一标识名
    - description: 工具功能描述
    - execute(): 执行工具逻辑，返回 ToolResult
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """工具唯一标识名"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """工具功能描述"""
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具逻辑

        Args:
            **kwargs: 工具参数（由具体工具定义）

        Returns:
            ToolResult: 执行结果，包含 success、data、error、recoverable 字段
        """
        ...
