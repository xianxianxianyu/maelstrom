# P2-03: Phase Router — 统一入口路由

## 依赖
- P2-00（意图分类器 — classify_intent）
- P2-01（反问协议 — ClarificationRequest）
- P2-02（EvidenceMemory — SessionMemorySummary）
- P1-11（Gap Engine API）
- P0-06（QA Chat API）

## 目的
实现 Phase Router：统一的用户输入入口，根据意图分类结果将请求路由到对应的 engine 或服务。这是 Orchestration Runtime（L3）在 V0 的简化实现。

## 设计原则
- Phase Router 不是一个独立的 engine，而是一个轻量路由层
- 它不处理业务逻辑，只做分类 → 路由 → 转发
- V0 阶段不实现 DAG Template Selector / Budget Controller，只做最简路由

## 执行方法

### 1. Router Schema — `src/maelstrom/schemas/router.py`

```python
class RouteDecision(BaseModel):
    intent: ClassifiedIntent
    target: Literal["gap_engine", "qa_chat", "clarification", "gap_followup", "share_to_qa", "config"]
    session_id: str
    payload: dict = {}    # 传递给目标的额外参数

class RouterResponse(BaseModel):
    """统一的路由响应，前端根据 response_type 决定渲染方式"""
    response_type: Literal["stream", "clarification", "redirect", "error"]
    stream_url: str | None = None           # SSE 流地址
    clarification: ClarificationRequest | None = None
    redirect_path: str | None = None        # 前端路由跳转
    error_message: str | None = None
```

### 2. Phase Router 服务 — `src/maelstrom/services/phase_router.py`

```python
async def route(
    session_id: str,
    user_input: str,
    clarification_reply: dict | None = None,  # 反问回复
) -> RouterResponse:
    # 0. 如果是反问回复，解析并获取意图
    if clarification_reply:
        intent = await resolve_clarification(clarification_reply)
    else:
        # 1. 构建 SessionContext
        context = await _build_session_context(session_id)
        # 2. 分类意图
        intent = await classify_intent(user_input, context)

    # 3. 路由决策
    if intent.intent == IntentType.clarification_needed:
        clar = await generate_clarification(user_input, session_id)
        return RouterResponse(response_type="clarification", clarification=clar)

    if intent.intent == IntentType.gap_discovery:
        topic = intent.extracted_topic or user_input
        run_id = await start_gap_run(session_id, topic)
        return RouterResponse(
            response_type="stream",
            stream_url=f"/api/gap/run/{run_id}/stream",
        )

    if intent.intent == IntentType.qa_chat:
        msg_id = await start_ask(session_id, user_input)
        return RouterResponse(
            response_type="stream",
            stream_url=f"/api/chat/ask/{msg_id}/stream",
        )

    if intent.intent == IntentType.gap_followup:
        # 将 gap_ref 注入到 QA 问题中，附加上下文
        msg_id = await start_ask(session_id, user_input)
        return RouterResponse(
            response_type="stream",
            stream_url=f"/api/chat/ask/{msg_id}/stream",
        )

    if intent.intent == IntentType.share_to_qa:
        return RouterResponse(
            response_type="redirect",
            redirect_path="/gap",  # 引导用户到 Gap 页面操作 share-to-qa
        )

    if intent.intent == IntentType.config:
        return RouterResponse(
            response_type="redirect",
            redirect_path="/settings",
        )
```

### 3. `_build_session_context` 辅助函数

从 EvidenceMemory 和 DB 构建 SessionContext：
```python
async def _build_session_context(session_id: str) -> SessionContext:
    db = await get_db()
    session = await session_repo.get_session(db, session_id)
    summary = await evidence_memory.get_session_summary(session_id)
    # 查询最近一条 chat_message 的意图（如果有标记）
    recent_intent = await _get_recent_intent(db, session_id)
    return SessionContext(
        session_id=session_id,
        has_gap_runs=summary.gap_count > 0,
        has_indexed_docs=summary.paper_count > 0,
        recent_intent=recent_intent,
    )
```

### 4. 统一 API 端点 — `src/maelstrom/api/router.py`

```python
router = APIRouter(prefix="/api/router", tags=["router"])

@router.post("/input")
async def handle_input(body: RouterInput):
    """统一入口：接收用户输入，返回路由决策"""
    response = await phase_router.route(
        session_id=body.session_id,
        user_input=body.user_input,
        clarification_reply=body.clarification_reply,
    )
    return response

class RouterInput(BaseModel):
    session_id: str
    user_input: str = ""
    clarification_reply: dict | None = None
```

### 5. 注册到 FastAPI app

在 `main.py` 中 `include_router(router_api.router)`。

## 验收条件
- `POST /api/router/input` 接收用户输入并返回 RouterResponse
- gap_discovery 意图 → 返回 stream_url 指向 gap SSE
- qa_chat 意图 → 返回 stream_url 指向 chat SSE
- clarification_needed → 返回 clarification 对象
- config 意图 → 返回 redirect_path="/settings"
- share_to_qa 意图 → 返回 redirect_path="/gap"
- 反问回复正确解析并路由

## Unit Test
- `test_route_gap_discovery`: 输入 "分析 NLP 研究空白" → response_type="stream", stream_url 包含 "/api/gap/"
- `test_route_qa_chat`: 输入 "这篇论文的方法？" → response_type="stream", stream_url 包含 "/api/chat/"
- `test_route_clarification`: 模糊输入 → response_type="clarification"
- `test_route_config`: 输入 "切换模型" → response_type="redirect", redirect_path="/settings"
- `test_route_share_to_qa`: 输入 "把论文加到问答" → response_type="redirect", redirect_path="/gap"
- `test_route_gap_followup`: 输入 "第一个 gap 展开说说" → response_type="stream"（走 QA）
- `test_clarification_reply_resolves`: 提交 clarification_reply → 正确路由到目标
- `test_session_context_built`: 验证 _build_session_context 正确读取 EvidenceMemory summary
- `test_api_endpoint_registered`: GET /docs 中包含 /api/router/input
