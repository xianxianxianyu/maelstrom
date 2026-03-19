# P3-01: Synthesis Engine 图定义 + SynthesisService

## 依赖
- P3-00（Synthesis Schemas — SynthesisRunState）
- P1-05（Gap Engine 图定义模式参考）

## 目的
定义 Synthesis Engine 的 7 节点有向图结构和 SynthesisService（后台任务编排 + SSE 事件推送），复用 Gap Engine 的 builder/service 模式。

## 执行方法

### 1. 图定义 — `src/maelstrom/graph/synthesis_engine.py`

7 个节点函数签名（初始为 pass-through 占位）：
- `targeted_retrieval` — 针对 gap/topic 做精准检索
- `relevance_filtering` — 过滤噪声论文
- `claim_extraction` — 提取 Claim + Evidence
- `citation_binding` — 绑定 claim 到原文 span
- `conflict_analysis` — 共识/冲突分析
- `feasibility_review` — 可行性评估
- `report_assembly` — 组装 ReviewReport + FeasibilityMemo

Edge 路由：
- `targeted_retrieval` → 有论文 → `relevance_filtering`，无论文 → `error_end`
- 其余节点线性连接

### 2. 图构建 — `src/maelstrom/graph/synthesis_builder.py`

```python
class SynthesisEngineGraph:
    """Custom runner for Synthesis Engine, mirrors GapEngineGraph pattern."""
    NODES = [
        "targeted_retrieval", "relevance_filtering", "claim_extraction",
        "citation_binding", "conflict_analysis", "feasibility_review",
        "report_assembly",
    ]

    async def run(self, state: dict, node_callback=None) -> dict:
        for node_name in self.NODES:
            if node_callback:
                await node_callback(node_name, "start")
            node_fn = getattr(nodes_module, node_name)
            state = await node_fn(state)
            if state.get("error"):
                break
            if node_callback:
                await node_callback(node_name, "complete")
            # 路由检查：targeted_retrieval 后无论文则中断
            if node_name == "targeted_retrieval" and not state.get("targeted_papers"):
                state["error"] = "No papers found for synthesis"
                break
        return state
```

### 3. SynthesisService — `src/maelstrom/services/synthesis_service.py`

复用 gap_service 的模式：
- `start_run(session_id, topic, gap_id, profile)` → 创建 DB 记录 + 启动后台 asyncio task
- `_execute_run(run_id, ...)` → 依次执行 7 个节点，每步推送 SSE 事件
- `get_status(run_id)` / `get_result(run_id)` — 查询状态和结果
- `subscribe(run_id)` / `unsubscribe(run_id, queue)` — SSE pub/sub
- `stream_events(run_id)` — 异步生成器，yield SSE 事件

SSE 事件类型（复用 Gap Engine 模式）：
- `step_start` / `step_complete` — 每个节点开始/完成
- `papers_found` — targeted_retrieval 完成后
- `claims_extracted` — claim_extraction 完成后（增量推送）
- `conflict_found` — conflict_analysis 发现冲突时
- `result` — 最终 ReviewReport + FeasibilityMemo
- `error` / `__done__`

### 4. DB 表 — synthesis_runs

在 `migrations.py` 中新增：
```sql
CREATE TABLE IF NOT EXISTS synthesis_runs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    source_gap_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    result_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    completed_at TEXT
);
```

### 5. synthesis_run_repo — `src/maelstrom/db/synthesis_run_repo.py`

CRUD 操作：create / get / update_status / update_result / list_by_session

## 验收条件
- SynthesisEngineGraph 包含 7 个节点
- 占位节点可执行（pass-through 不报错）
- targeted_retrieval 无论文时路由到 error
- SynthesisService 可启动后台 run 并推送 SSE 事件
- synthesis_runs 表正确创建
- synthesis_run_repo CRUD 正常

## Unit Test
- `test_graph_node_count`: 7 个节点
- `test_graph_passthrough`: 占位节点执行不报错
- `test_route_no_papers`: targeted_retrieval 无论文 → error
- `test_service_start_run`: 创建 run 记录 + 返回 run_id
- `test_service_sse_events`: mock 执行 → 收到 step_start/step_complete 事件
- `test_synthesis_run_repo_crud`: create/get/update/list 正常
- `test_db_table_created`: synthesis_runs 表存在
