# Orchestration Runtime

## 1. Module Definition

Orchestration Runtime 是系统的控制面。  
它不关心具体研究领域内容，而关心：**当前阶段是什么、该跑哪个 engine、用哪个 DAG 模板、哪些节点允许 agent 自主、哪里要停下来给人看。**

---

## 2. Core Responsibilities

1. 路由 phase → engine
2. 选择 engine-specific DAG template
3. 管理 session / thread / checkpoints
4. 控制 handoff / parallel execution / retry / recovery
5. 实现 budget / timeout / approval / interrupt
6. 把运行期事件写入 trace bus

---

## 3. Internal Submodules

| Submodule | Purpose |
|---|---|
| Phase Router | 根据请求和当前 artifacts 选择目标 phase / engine |
| DAG Template Selector | 选择具体 subgraph 模板 |
| Local Orchestrator | 在 subgraph 内调度节点 |
| Handoff Manager | 控制 agent 间委派 |
| Parallel Executor | 并行检索、并行 compare、并行 validate |
| Retry / Recovery | 重试策略、回滚与异常恢复 |
| Session / Thread Manager | 持久化会话与 checkpoint |
| Budget Controller | token / latency / tool budget |
| HITL Interrupt Manager | 在审批点中断并等待人工 |

---

## 4. Phase Routing Rules

```text
if input is broad topic and no validated gap:
    route -> Gap Engine
elif selected gap exists but no feasibility report:
    route -> Synthesis Engine
elif feasibility approved but no plan:
    route -> Planning Engine
elif plan approved and run data exists:
    route -> Experiment Engine
else:
    ask governance layer for clarification or resume existing phase
```

---

## 5. Template Strategy

### Why templates?
- 保持流程稳定
- 限制 agent 的自由度
- 便于 trace / eval / replay
- 便于做 A/B 测试和版本演进

### Template Examples
- `gap_discovery_v1`
- `gap_discovery_with_survey_first_v2`
- `review_conflict_focused_v1`
- `planning_resource_constrained_v1`
- `experiment_reflection_heavy_v1`

---

## 6. State Model

### `SessionState`
```json
{
  "session_id": "sess-001",
  "current_phase": "grounding",
  "active_engine": "synthesis",
  "current_template": "review_conflict_focused_v1",
  "artifact_refs": ["gap-001", "rev-001"],
  "pending_approval": null,
  "budgets": {
    "max_tokens": 500000,
    "max_runtime_s": 900
  }
}
```

### Checkpoint Strategy
- checkpoint after each node
- force checkpoint before human approval
- force checkpoint before external side-effecting tool calls
- support rollback to last approved checkpoint

---

## 7. Node Types

| Node Type | Description | Example |
|---|---|---|
| deterministic | 固定逻辑 / code node | normalize metadata |
| skill | 调用可复用 procedure | claim extraction skill |
| agentic | 需要动态 reasoning | gap hypothesis generation |
| tool | 外部工具 / MCP resource/tool | search paper server |
| approval | 人工审批节点 | approve topic candidate |

---

## 8. Prompt Engineering for the Orchestrator

### 8.1 Phase Router Prompt
```text
你是 Phase Router。
你的任务不是回答研究问题，而是决定接下来应该激活哪个 engine。
只允许输出：
- phase
- engine
- template
- reason
- required_inputs
```

### 8.2 Local Orchestrator Prompt
```text
你是当前 subgraph 的本地编排器。
请根据：
- 当前节点状态
- 已有 artifacts
- 预算限制
- approval policy
决定：
1. 下一节点
2. 是否并行
3. 是否需要转交给某个 specialist agent
4. 是否必须请求人工确认
```

---

## 9. Communication with Other Modules

### Inputs
- task requests from Workspace
- memory summaries from Memory Substrate
- policy configs from Governance

### Outputs
- engine invocations
- node execution requests
- approval requests
- trace events
- checkpoint writes

---

## 10. Reuse-First Recommendations

| Need | Reuse Candidate | Notes |
|---|---|---|
| graph/subgraph/checkpoints | LangGraph | 首选 |
| event-driven business flow | CrewAI Flows | 可参考，但不必主导 |
| team orchestration baseline | AutoGen | 用于实验和比较 |
| generalized open-ended multi-agent routing | Magentic-One pattern | 只借鉴，不建议直接套用 |
