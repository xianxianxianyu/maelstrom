"""任务管理器 — 跟踪运行中的翻译任务，支持取消和清理"""
import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class TaskInfo:
    """运行中的任务信息"""
    task_id: str
    filename: str
    asyncio_tasks: list[asyncio.Task] = field(default_factory=list)
    temp_path: Optional[Path] = None
    cancelled: bool = False


class TaskManager:
    """管理所有运行中的翻译任务"""

    def __init__(self):
        self._tasks: Dict[str, TaskInfo] = {}

    def create_task(self, filename: str) -> TaskInfo:
        task_id = uuid.uuid4().hex[:12]
        info = TaskInfo(task_id=task_id, filename=filename)
        self._tasks[task_id] = info
        logger.info(f"📋 任务创建: {task_id} ({filename})")
        return info

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        return self._tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """取消任务：cancel 所有 asyncio.Task + 清理临时文件"""
        info = self._tasks.get(task_id)
        if not info:
            return False

        info.cancelled = True
        for t in info.asyncio_tasks:
            if not t.done():
                t.cancel()
        logger.info(f"🛑 任务取消: {task_id} ({info.filename})")

        # 清理临时文件
        self._cleanup(info)
        return True

    def finish_task(self, task_id: str):
        """任务完成，清理记录和临时文件"""
        info = self._tasks.pop(task_id, None)
        if info:
            self._cleanup(info)
            logger.info(f"🧹 任务清理: {task_id}")

    def cancel_all(self):
        """取消所有运行中的任务"""
        for task_id in list(self._tasks.keys()):
            self.cancel_task(task_id)
        self._tasks.clear()

    def list_tasks(self) -> list[dict]:
        return [
            {"task_id": t.task_id, "filename": t.filename, "cancelled": t.cancelled}
            for t in self._tasks.values()
        ]

    def _cleanup(self, info: TaskInfo):
        if info.temp_path and info.temp_path.exists():
            try:
                info.temp_path.unlink()
            except Exception as e:
                logger.warning(f"清理临时文件失败: {info.temp_path}, {e}")


# 模块级单例
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
