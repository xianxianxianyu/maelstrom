# P2-04: 统一 Chat 入口改造 + 路由集成

## 依赖
- P2-03（Phase Router — route()）
- P0-06（QA Chat API — /api/chat/ask）
- P1-11（Gap Engine API — /api/gap/run）

## 目的
将现有的 `/api/chat/ask` 从"直接调 paper-qa"改造为"先经 Phase Router 分类再转发"的统一入口。用户在 Chat 页面输入任何内容，系统自动判断意图并路由，无需用户手动切换页面。

## 设计决策
- 保留原有 `/api/chat/ask` 和 `/api/gap/run` 端点不变（向后兼容）
- 新增 `/api/router/input` 作为统一入口（P2-03 已定义）
- 前端 Chat 页面改为调用 `/api/router/input`，根据 `response_type` 决定后续行为

## 执行方法

### 1. Chat API 扩展 — `src/maelstrom/api/chat.py`

新增反问回复端点：
```python
@router.post("/clarify")
async def clarify(body: ClarifyInput):
    """处理用户对反问的回复"""
    response = await phase_router.route(
        session_id=body.session_id,
        user_input=body.freetext or "",
        clarification_reply={
            "request_id": body.request_id,
            "option_index": body.option_index,
            "freetext": body.freetext,
        },
    )
    return response

class ClarifyInput(BaseModel):
    session_id: str
    request_id: str
    option_index: int | None = None
    freetext: str | None = None
```

### 2. 意图标记持久化

在 `chat_repo` 中扩展 `chat_messages` 表，新增 `intent` 列（可选）：
```sql
ALTER TABLE chat_messages ADD COLUMN intent TEXT DEFAULT NULL;
```

通过 migration 兼容处理（`ALTER TABLE IF NOT EXISTS` 或 try/except）。

路由完成后，将分类结果写入 chat_messages：
```python
await chat_repo.create_chat_message(
    db, session_id, "system", f"[intent: {intent.intent.value}]",
    intent=intent.intent.value,
)
```

### 3. SessionContext 的 recent_intent 查询

```python
async def _get_recent_intent(db, session_id: str) -> IntentType | None:
    row = await db.execute(
        "SELECT intent FROM chat_messages WHERE session_id = ? AND intent IS NOT NULL ORDER BY created_at DESC LIMIT 1",
        (session_id,),
    )
    ...
```

## 验收条件
- `/api/chat/clarify` 端点正常工作
- 意图标记正确写入 chat_messages.intent 列
- `_get_recent_intent` 正确返回最近意图
- 原有 `/api/chat/ask` 和 `/api/gap/run` 端点不受影响（向后兼容）
- migration 对已有数据库兼容（ALTER TABLE 不报错）

## Unit Test
- `test_clarify_endpoint_option`: POST /api/chat/clarify + option_index → 返回 RouterResponse
- `test_clarify_endpoint_freetext`: POST /api/chat/clarify + freetext → 重新分类
- `test_intent_persisted`: 路由后 chat_messages 中有 intent 记录
- `test_recent_intent_query`: 写入 2 条不同 intent → 返回最新的
- `test_migration_idempotent`: 对已有表执行 ALTER TABLE 不报错
- `test_backward_compat_ask`: 直接调用 /api/chat/ask 仍正常工作
- `test_backward_compat_gap`: 直接调用 /api/gap/run 仍正常工作
