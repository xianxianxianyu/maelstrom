# Data, Observability, and Evaluation Foundation

## 1. Module Definition

这一层是系统可信性、复现性和可调试性的基础。  
如果没有这一层，前面的多 agent / DAG / skills 都会退化成不可审计的黑箱。

---

## 2. Core Components

- Artifact Store
- Evidence Graph
- Document Index / Retrieval Layer
- Run Records
- Trace / Event Bus
- Eval Harness
- Metrics Store
- Versioning / Provenance / Audit

---

## 3. Artifact Store

### Purpose
统一保存所有 typed artifacts，并支持：
- versioning
- lineage
- schema validation
- lifecycle status（draft/approved/archived）

### Storage Suggestion
- metadata: relational DB
- content blobs: object store
- search index: vector + keyword hybrid

---

## 4. Evidence Graph

### Purpose
保存关键实体之间的关系，而不是只存平铺 JSON。

### Suggested Relations
- `GapItem -> supported_by -> Evidence`
- `ReviewReport -> contains -> Claim`
- `ExperimentPlan -> addresses -> GapItem`
- `RunRecord -> executes -> ExperimentPlan`
- `Conclusion -> inferred_from -> RunRecord`
- `Conclusion -> supported_by -> Evidence`

### Benefit
- 便于 lineage 查询
- 便于 evidence-aware retrieval
- 便于 unsupported claim 检查

---

## 5. Trace and Event Bus

### Why it matters
所有节点、tools、skills、handoffs、approvals 都应该发事件。

### Suggested Event Types
- `phase_started`
- `engine_selected`
- `node_entered`
- `node_completed`
- `tool_called`
- `skill_loaded`
- `artifact_created`
- `approval_requested`
- `approval_resolved`
- `claim_flagged`
- `run_completed`
- `run_failed`

### Example Event
```json
{
  "event_id": "evt-001",
  "trace_id": "trace-001",
  "timestamp": "...",
  "event_type": "artifact_created",
  "module": "synthesis_engine",
  "payload": {
    "artifact_type": "ReviewReport",
    "artifact_id": "rev-001"
  }
}
```

---

## 6. Evaluation Harness

### What to Evaluate
| Dimension | Example Metrics |
|---|---|
| Gap quality | relevance, novelty alignment, human accept rate |
| Synthesis quality | citation precision, unsupported-claim rate, coverage |
| Planning quality | completeness, feasibility, edit ratio |
| Experiment inference quality | conclusion-grounding score, false conclusion rate |
| Runtime quality | P95 latency, tool success rate, retry rate, cost per run |

### Eval Data Sources
- historical runs
- golden task set
- human review labels
- trace replays
- failure archives

### Eval Modes
- offline replay
- regression suite
- shadow evaluation
- human adjudication

---

## 7. Versioning and Provenance

必须记录：
- prompt/template version
- skill version
- model version
- code version
- data version
- tool profile version
- artifact lineage
- approval decisions

这一步是后续“为什么上周可以、这周不行”的核心定位依据。

---

## 8. Prompt Templates

### 8.1 Unsupported Claim Eval Prompt
```text
你是评测器。
请检查目标 artifact 中的每个 claim 是否有足够 evidence / run record 支撑。
输出：
- supported
- weakly_supported
- unsupported
并给出原因。
```

### 8.2 Plan Completeness Eval Prompt
```text
请检查实验计划是否完整覆盖：
- objective
- baseline
- metric
- ablation
- risk
- reproducibility items
输出缺失项清单。
```

---

## 9. Communication with Other Modules

- 接收所有 engine 的 artifacts
- 接收 runtime 的 trace events
- 向 Workspace 提供 trace explorer / lineage view
- 向 Governance 提供 eval dashboards
- 向 Memory 提供 evidence-aware retrieval foundation

---

## 10. Reuse-First Recommendations

| Need | Reuse Candidate | Notes |
|---|---|---|
| workflow traces | OpenAI Agents SDK tracing / OpenTelemetry | 二选一或桥接 |
| graph checkpoints | LangGraph persistence | 很适合 session/thread/checkpoint |
| experiment tracking | MLflow / W&B / existing platform | 不建议重造 |
| retrieval | vector DB + keyword search | file search/hybrid retrieval concepts 可参考 |
