# P2-07: Session Phase 状态追踪

## 依赖
- P2-03（Phase Router — RouteDecision）
- P0-03（Session 管理 — sessions 表）

## 目的
为 Session 增加 phase 状态追踪，记录当前会话处于研究流程的哪个阶段（ideation / grounding / planning / execution）。这是 Orchestration Runtime 状态模型在 V0 的简化实现，为未来 Synthesis Engine 等后续 engine 的路由提供基础。

## 执行方法

### 1. Phase 枚举 — `src/maelstrom/schemas/common.py`

```python
class ResearchPhase(str, Enum):
    ideation = "ideation"           # Gap Engine 阶段
    grounding = "grounding"         # Synthesis Engine 阶段（V1）
    planning = "planning"           # Planning Engine 阶段（V1+）
    execution = "execution"         # Experiment Engine 阶段（V1+）
```

### 2. DB Migration — sessions 表扩展

```sql
ALTER TABLE sessions ADD COLUMN current_phase TEXT DEFAULT 'ideation';
ALTER TABLE sessions ADD COLUMN phase_updated_at TEXT DEFAULT NULL;
```

### 3. Phase 转换规则 — `src/maelstrom/services/phase_tracker.py`

```python
# V0 阶段只实现 ideation 内的状态追踪
# 未来 V1 扩展 grounding / planning / execution

async def update_phase_on_route(session_id: str, intent: ClassifiedIntent) -> None:
    """路由完成后更新 session phase"""
    db = await get_db()
    if intent.intent == IntentType.gap_discovery:
        await _set_phase(db, session_id, ResearchPhase.ideation)
    # V1: gap 完成 + 用户选择 gap → grounding
    # V1: review 完成 + 用户确认 → planning

async def get_current_phase(session_id: str) -> ResearchPhase:
    db = await get_db()
    row = await db.execute_fetchone(
        "SELECT current_phase FROM sessions WHERE id = ?", (session_id,)
    )
    return ResearchPhase(row[0]) if row else ResearchPhase.ideation
```

### 4. Session API 扩展

在 `GET /api/sessions/{id}` 的返回中包含 `current_phase` 字段。

### 5. Phase Router 集成

在 `phase_router.route()` 末尾调用 `update_phase_on_route()`。

## 验收条件
- `ResearchPhase` 枚举包含 4 个阶段
- sessions 表新增 `current_phase` 列，默认 `ideation`
- gap_discovery 路由后 session phase 更新为 `ideation`
- `GET /api/sessions/{id}` 返回 `current_phase`
- migration 对已有数据兼容

## Unit Test
- `test_research_phase_enum`: 验证 4 个阶段值
- `test_session_default_phase`: 新建 session → current_phase = "ideation"
- `test_update_phase_on_gap`: gap_discovery 路由 → phase = "ideation"
- `test_get_current_phase`: 设置 phase 后查询正确
- `test_session_api_includes_phase`: GET /api/sessions/{id} 响应包含 current_phase
- `test_migration_existing_sessions`: 已有 session 获得默认 phase 值
