"""EventBus — 进程内事件总线，基于 asyncio.Queue

提供 subscribe/unsubscribe/publish 方法，用于 Agent 执行过程中
通过 SSE 向前端推送实时进度事件。

Requirements: 1.7, 5.6
"""

from __future__ import annotations

import asyncio


class EventBus:
    """进程内事件总线，基于 asyncio.Queue

    Agent 通过 AgentContext 持有 EventBus 引用，在执行过程中
    调用 publish() 发布进度事件。SSE 端点通过 subscribe() 获取
    asyncio.Queue，消费事件并推送给前端。

    Usage::

        bus = EventBus()
        queue = bus.subscribe("task-001")

        # Agent 侧发布事件
        await bus.publish("task-001", {"stage": "translating", "progress": 50})

        # SSE 端点侧消费事件
        event = await queue.get()

        # 清理
        bus.unsubscribe("task-001", queue)
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, task_id: str) -> asyncio.Queue:
        """订阅某任务的事件流

        Args:
            task_id: 翻译任务唯一标识

        Returns:
            asyncio.Queue 实例，用于接收该任务的事件
        """
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(task_id, []).append(queue)
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue) -> None:
        """取消订阅

        从指定任务的订阅者列表中移除给定的 queue。
        如果 task_id 不存在或 queue 不在列表中，静默忽略。

        Args:
            task_id: 翻译任务唯一标识
            queue: 之前通过 subscribe() 获取的 asyncio.Queue 实例
        """
        if task_id in self._subscribers:
            self._subscribers[task_id] = [
                q for q in self._subscribers[task_id] if q is not queue
            ]

    async def publish(self, task_id: str, event: dict) -> None:
        """发布事件到所有订阅者

        将事件放入该 task_id 下所有订阅者的 queue 中。
        如果没有订阅者，事件将被静默丢弃。

        Args:
            task_id: 翻译任务唯一标识
            event: 事件字典，通常包含 agent、stage、progress 等字段
        """
        for queue in self._subscribers.get(task_id, []):
            await queue.put(event)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """获取全局 EventBus 单例

    Returns:
        全局唯一的 EventBus 实例
    """
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
