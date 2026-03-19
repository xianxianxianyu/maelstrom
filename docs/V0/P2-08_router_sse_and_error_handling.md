# P2-08: Router SSE 进度协议 + 错误处理

## 依赖
- P2-03（Phase Router — RouterResponse）
- P2-01（反问协议 — ClarificationRequest）
- P1-12（Gap SSE — step_start / step_complete 事件）

## 目的
为 Phase Router 定义统一的 SSE 进度协议，让前端能用一套逻辑处理所有路由结果的流式反馈。同时实现路由层的错误处理和降级策略。

## 执行方法

### 1. 统一 SSE 事件协议

Phase Router 在路由成功后，先推送一个 `route_resolved` 事件，再转发目标 engine 的 SSE 流：

```json
{"event": "route_resolved", "data": {"intent": "gap_discovery", "target": "gap_engine", "confidence": 0.85}}
```

前端收到 `route_resolved` 后可立即展示意图标签（如 "正在分析研究缺口..."）。

对于 clarification，推送：
```json
{"event": "clarification", "data": {"request_id": "...", "question": "...", "options": [...]}}
```

### 2. 统一 SSE 端点 — `src/maelstrom/api/router.py`

新增流式端点：
```python
@router.post("/input/stream", status_code=200)
async def handle_input_stream(body: RouterInput):
    """统一入口的 SSE 版本：路由 + 转发目标流"""
    async def event_generator():
        response = await phase_router.route(body.session_id, body.user_input, body.clarification_reply)

        # 推送路由决策
        yield {"event": "route_resolved", "data": json.dumps({
            "response_type": response.response_type,
            "intent": response.intent.intent.value if hasattr(response, 'intent') else None,
        })}

        if response.response_type == "clarification":
            yield {"event": "clarification", "data": response.clarification.model_dump_json()}
            yield {"event": "__done__", "data": "{}"}
            return

        if response.response_type == "redirect":
            yield {"event": "redirect", "data": json.dumps({"path": response.redirect_path})}
            yield {"event": "__done__", "data": "{}"}
            return

        if response.response_type == "error":
            yield {"event": "error", "data": json.dumps({"message": response.error_message})}
            yield {"event": "__done__", "data": "{}"}
            return

        # stream 类型：转发目标 engine 的 SSE 事件
        if response.response_type == "stream":
            async for event in _proxy_stream(response.stream_url):
                yield event
            yield {"event": "__done__", "data": "{}"}

    return EventSourceResponse(event_generator())
```

### 3. 错误处理与降级

```python
async def route_with_fallback(session_id: str, user_input: str, ...) -> RouterResponse:
    try:
        return await phase_router.route(session_id, user_input, ...)
    except LLMConfigError:
        return RouterResponse(response_type="error", error_message="请先配置 LLM（设置页面）")
    except asyncio.TimeoutError:
        # 分类超时 → 降级为 qa_chat
        msg_id = await start_ask(session_id, user_input)
        return RouterResponse(response_type="stream", stream_url=f"/api/chat/ask/{msg_id}/stream")
    except Exception as e:
        return RouterResponse(response_type="error", error_message=f"路由失败: {str(e)}")
```

降级策略：
- LLM 未配置 → 返回 error + 提示配置
- 分类器超时 → 降级为 qa_chat（最安全的默认行为）
- EvidenceMemory 查询失败 → 跳过上下文注入，继续路由
- 目标 engine 启动失败 → 返回 error + 具体原因

## 验收条件
- `POST /api/router/input/stream` 返回 SSE 流
- 首个事件为 `route_resolved`，包含意图信息
- clarification 通过 SSE 推送而非 JSON 响应
- stream 类型正确转发目标 engine 的 SSE 事件
- 所有 SSE 流以 `__done__` 结束
- LLM 未配置时返回友好错误提示
- 分类超时时降级为 qa_chat
- 异常不导致 SSE 流中断（总是有 error 事件 + __done__）

## Unit Test
- `test_stream_route_resolved_event`: 任意输入 → 首个事件为 route_resolved
- `test_stream_clarification_event`: 模糊输入 → clarification 事件 + __done__
- `test_stream_redirect_event`: config 输入 → redirect 事件 + __done__
- `test_stream_proxy_gap`: gap 输入 → route_resolved + gap engine 事件流 + __done__
- `test_stream_proxy_chat`: qa 输入 → route_resolved + chat 事件流 + __done__
- `test_fallback_no_llm_config`: 无 LLM 配置 → error 事件
- `test_fallback_classifier_timeout`: 分类超时 → 降级为 chat stream
- `test_fallback_exception`: 未知异常 → error 事件 + __done__（不挂起）
