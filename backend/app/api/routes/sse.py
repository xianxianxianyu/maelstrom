"""SSE 端点 — 推送翻译任务实时进度事件

通过 Server-Sent Events 向前端推送翻译进度，包括当前 Agent、
执行阶段和完成百分比。

Requirements: 1.7, 5.6, 6.1
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agent.event_bus import get_event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sse", tags=["sse"])


async def _event_generator(task_id: str) -> AsyncGenerator[str, None]:
    """生成 SSE 事件流

    订阅 EventBus 中指定 task_id 的事件，逐条以 SSE 格式 yield。
    当收到 stage=="complete" 的事件时发送该事件后结束流。
    每 5 秒检查一次任务是否仍在运行，如果任务已结束但没收到 complete 事件，
    则主动发送完成事件并关闭流。

    Args:
        task_id: 翻译任务唯一标识
    """
    bus = get_event_bus()
    queue = bus.subscribe(task_id)

    # 发送初始连接事件
    init_event = {
        "agent": "system",
        "stage": "connected",
        "progress": 0,
        "detail": {"message": "SSE 已连接，等待翻译进度..."},
    }
    yield f"data: {json.dumps(init_event)}\n\n"

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=5)
            except asyncio.TimeoutError:
                # 每 5 秒检查任务是否仍在运行
                from app.services.task_manager import get_task_manager
                tm = get_task_manager()
                task_info = tm.get_task(task_id)
                if task_info is None:
                    # 任务已结束（可能完成或失败），但没收到 complete 事件
                    # 检查是否有结果
                    from app.api.routes.pdf import _task_results
                    if task_id in _task_results:
                        result = _task_results[task_id]
                        if result.get("error"):
                            error_event = {
                                "agent": "system",
                                "stage": "error",
                                "progress": -1,
                                "detail": {"message": result["error"]},
                            }
                            yield f"data: {json.dumps(error_event)}\n\n"
                        else:
                            done_event = {
                                "agent": "orchestrator",
                                "stage": "complete",
                                "progress": 100,
                            }
                            yield f"data: {json.dumps(done_event)}\n\n"
                    else:
                        done_event = {
                            "agent": "orchestrator",
                            "stage": "complete",
                            "progress": 100,
                        }
                        yield f"data: {json.dumps(done_event)}\n\n"
                    logger.info("SSE 任务已结束（补发 complete）: task_id=%s", task_id)
                    break
                # 任务仍在运行，发送心跳保持连接
                heartbeat = {
                    "agent": "system",
                    "stage": "heartbeat",
                    "progress": -1,
                }
                yield f"data: {json.dumps(heartbeat)}\n\n"
                continue

            # 正常事件：以 SSE 格式发送
            yield f"data: {json.dumps(event)}\n\n"

            # 完成事件：发送后关闭流
            if event.get("stage") == "complete" and event.get("agent") == "orchestrator":
                logger.info("SSE 完成: task_id=%s", task_id)
                break
    except asyncio.CancelledError:
        # 客户端断开连接
        logger.info("SSE 客户端断开: task_id=%s", task_id)
    finally:
        bus.unsubscribe(task_id, queue)
        logger.debug("SSE 已取消订阅: task_id=%s", task_id)


@router.get("/translation/{task_id}")
async def translation_sse(task_id: str):
    """SSE 端点：推送翻译任务进度

    前端通过 EventSource 连接此端点，实时接收翻译进度事件。
    事件格式为 JSON，包含 agent、stage、progress 等字段。

    Args:
        task_id: 翻译任务唯一标识

    Returns:
        StreamingResponse: SSE 事件流 (text/event-stream)
    """
    return StreamingResponse(
        _event_generator(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _qa_event_generator(trace_id: str) -> AsyncGenerator[str, None]:
    from app.api.routes.qa_v1 import _get_kernel

    bus = get_event_bus()
    queue = bus.subscribe(trace_id)
    kernel = _get_kernel()
    logger.info("qa_sse_stream_start", extra={"trace_id": trace_id})

    sent_seq: set[int] = set()

    init_event = {
        "type": "stream.connected",
        "trace_id": trace_id,
        "progress": 0,
    }
    yield f"data: {json.dumps(init_event)}\n\n"

    replay = kernel.get_execution_events(trace_id)
    for event in replay:
        seq = int(event.get("seq") or 0)
        if seq > 0:
            sent_seq.add(seq)
        yield f"data: {json.dumps(event)}\n\n"

    if replay and replay[-1].get("type") == "final.ready":
        done_event = {"type": "stream.complete", "trace_id": trace_id, "progress": 100}
        yield f"data: {json.dumps(done_event)}\n\n"
        bus.unsubscribe(trace_id, queue)
        logger.info("qa_sse_stream_replay_complete", extra={"trace_id": trace_id, "replayed": len(replay)})
        return

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=10)
            except asyncio.TimeoutError:
                heartbeat = {
                    "type": "heartbeat",
                    "trace_id": trace_id,
                    "progress": -1,
                }
                yield f"data: {json.dumps(heartbeat)}\n\n"
                continue

            seq = int(event.get("seq") or 0)
            if seq and seq in sent_seq:
                continue
            if seq:
                sent_seq.add(seq)
            yield f"data: {json.dumps(event)}\n\n"

            if event.get("type") == "final.ready":
                done_event = {"type": "stream.complete", "trace_id": trace_id, "progress": 100}
                yield f"data: {json.dumps(done_event)}\n\n"
                logger.info("qa_sse_stream_complete", extra={"trace_id": trace_id})
                break
    except asyncio.CancelledError:
        logger.info("QA SSE client disconnected: trace_id=%s", trace_id)
    finally:
        bus.unsubscribe(trace_id, queue)


@router.get("/qa/{trace_id}")
async def qa_execution_sse(trace_id: str):
    return StreamingResponse(
        _qa_event_generator(trace_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
