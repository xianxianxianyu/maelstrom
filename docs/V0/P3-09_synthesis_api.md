# P3-09: Synthesis Engine API 端点

## 依赖
- P3-01（SynthesisService — start_run / get_status / get_result / stream_events）
- P3-08（report_assembly — 完整 pipeline 可执行）
- P2-03（Phase Router — 路由集成）

## 目的
为 Synthesis Engine 提供 REST API 端点，复用 Gap Engine API 的模式。同时将 Synthesis 路由集成到 Phase Router。

## 执行方法

### 1. API 端点 — `src/maelstrom/api/synthesis.py`

```python
router = APIRouter(prefix="/api/synthesis", tags=["synthesis"])

# 启动 synthesis run
@router.post("/run", status_code=202)
async def start_run(body: SynthesisRunInput):
    """
    body: {
        session_id: str,
        topic: str,              # 直接输入 topic
        gap_id: str | None,      # 或从 Gap 结果选择
        profile_slug: str | None
    }
    → 202 + { run_id }
    """

# 查询状态
@router.get("/run/{run_id}/status")
async def get_status(run_id: str): ...

# 获取结果
@router.get("/run/{run_id}/result")
async def get_result(run_id: str):
    """返回 ReviewReport + FeasibilityMemo，未完成时 409"""

# SSE 流
@router.get("/run/{run_id}/stream")
async def stream(run_id: str):
    """SSE 事件流：step_start/step_complete/claims_extracted/conflict_found/result/__done__"""

# 获取 claims
@router.get("/run/{run_id}/claims")
async def get_claims(run_id: str):
    """返回该 run 提取的所有 Claim[]"""

# 获取 conflicts
@router.get("/run/{run_id}/conflicts")
async def get_conflicts(run_id: str):
    """返回 ConsensusPoint[] + ConflictPoint[]"""

# 列出 session 的 synthesis runs
@router.get("/runs")
async def list_runs(session_id: str, limit: int = 5): ...
```

### 2. Phase Router 集成

在 `intent_classifier.py` 中新增意图：
```python
class IntentType(str, Enum):
    ...
    synthesis = "synthesis"  # 用户想做文献综述/可行性分析
```

关键词规则新增：
- `synthesis` 关键词：`文献综述|综述分析|可行性|feasibility|review report|深入分析|立项评估`

在 `phase_router.py` 中新增路由分支：
```python
if intent.intent == IntentType.synthesis:
    topic = intent.extracted_topic or user_input
    run_id = await _start_synthesis_run(session_id, topic, gap_id=None)
    return RouterResponse(
        response_type="stream",
        stream_url=f"/api/synthesis/run/{run_id}/stream",
    )
```

### 3. Phase Tracker 集成

Synthesis 路由后更新 session phase 为 `grounding`。

### 4. 注册到 FastAPI app

在 `main.py` 中 `include_router(synthesis_router)`。

## 验收条件
- `POST /api/synthesis/run` 返回 202 + run_id
- `GET /api/synthesis/run/{id}/status` 返回状态
- `GET /api/synthesis/run/{id}/result` 返回 ReviewReport + FeasibilityMemo
- `GET /api/synthesis/run/{id}/stream` 返回 SSE 流
- `GET /api/synthesis/run/{id}/claims` 返回 Claim[]
- `GET /api/synthesis/run/{id}/conflicts` 返回 consensus + conflicts
- Phase Router 正确路由 synthesis 意图
- Session phase 更新为 grounding

## Unit Test
- `test_start_run_endpoint`: POST /api/synthesis/run → 202 + run_id
- `test_status_endpoint`: GET status → 正确状态
- `test_result_not_ready`: 未完成时 GET result → 409
- `test_claims_endpoint`: GET claims → Claim[]
- `test_conflicts_endpoint`: GET conflicts → consensus + conflicts
- `test_list_runs`: GET /api/synthesis/runs → 列表
- `test_router_synthesis_intent`: "帮我做文献综述" → 路由到 synthesis
- `test_phase_updated_to_grounding`: synthesis 路由后 phase = grounding
- `test_api_registered`: /docs 中包含 /api/synthesis/*
