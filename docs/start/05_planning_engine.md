# Planning Engine

## 1. Module Definition

Planning Engine 将经过可行性论证的研究方向转化为 **可执行实验计划**。  
它产出的重点不是“写得漂亮的文字”，而是 **可执行工件**：baseline matrix、metric design、ablation plan、resource/risk sheet、execution checklist。

---

## 2. Core Objectives

1. 将 gap / hypothesis 形式化为实验任务。
2. 自动推荐 baseline、数据集划分、评价指标、消融实验。
3. 分析风险、资源成本、可能失败模式。
4. 生成结构化实验计划，供 Experiment Engine 执行与跟踪。

---

## 3. Inputs / Outputs

### Inputs
- `ReviewReport`
- optional `Hypothesis`
- constraints（算力、数据许可、时间窗、设备）

### Outputs
- `ExperimentPlan`
- `BaselineMatrix`
- `AblationPlan`
- `ExecutionChecklist`
- optional `RiskMemo`

---

## 4. Recommended Pipeline

```mermaid
flowchart LR
  A["ReviewReport / Hypothesis"] --> B["Task Framing"]
  B --> C["Baseline Generation"]
  C --> D["Dataset / Protocol Selection"]
  D --> E["Metric and Ablation Design"]
  E --> F["Risk / Resource Estimation"]
  F --> G["Plan Validation"]
  G --> H["Plan Document Rendering"]
```

---

## 5. Agent vs Non-Agent Boundary

### Use Agent
- task framing
- baseline strategy proposal
- risk / failure anticipation
- final validation review

### Do Not Use Agent
- checklist rendering
- matrix formatting
- schema completion
- cost formula calculation
- schedule table generation

---

## 6. Internal Submodules

| Submodule | Purpose | Recommended style |
|---|---|---|
| Task Framer | 把方向写成任务/假设/成功判据 | planner agent |
| Baseline Generator | 推荐对照方法与比较维度 | planner + retriever |
| Protocol Selector | 数据集划分与实验协议 | workflow + skill |
| Metric/Ablation Designer | 指标与消融设计 | skill + critic |
| Risk Estimator | 算力/数据/工程风险分析 | critic agent |
| Plan Validator | 查漏补缺 | reviewer agent |
| Plan Renderer | 输出结构化文档 | deterministic renderer |

---

## 7. Artifact Schema Suggestions

### `ExperimentPlan`
```json
{
  "plan_id": "plan-001",
  "goal": "Evaluate robustness of artifact removal under ambulatory noise",
  "hypothesis": "Multi-branch denoising with artifact-aware routing improves robustness",
  "datasets": ["..."],
  "protocol": {
    "splits": "...",
    "controls": ["..."]
  },
  "baseline_matrix_id": "bm-001",
  "ablation_plan_id": "ab-001",
  "metrics": ["F1", "SNR_gain", "downstream_task_accuracy"],
  "approval_status": "pending"
}
```

### `BaselineMatrix`
```json
{
  "matrix_id": "bm-001",
  "rows": [
    {
      "baseline_name": "ICA-only",
      "purpose": "classical baseline",
      "must_have": true
    }
  ]
}
```

---

## 8. Skills to Implement

- `experiment_planner_skill`
- `baseline_matrix_skill`
- `protocol_selector_skill`
- `ablation_planner_skill`
- `risk_review_skill`

---

## 9. Prompt Templates

### 9.1 Task Framing Prompt
```text
你是 Experiment Task Framer。
请将下面的研究方向转成结构化实验任务：
- objective
- primary hypothesis
- success criteria
- required datasets
- key baselines
- critical risks

输出 JSON。
```

### 9.2 Baseline Matrix Prompt
```text
你是 Baseline Planner。
根据综述中的方法谱系、数据集与指标，给出：
1. 必做 baseline
2. 可选 baseline
3. 不建议作为主要 baseline 的方法
4. 每个 baseline 的比较价值

要求：不要列太多；优先高信息量、可执行。
```

### 9.3 Risk Review Prompt
```text
你是研究计划风控审查员。
请检查该实验计划是否存在：
- 隐含的数据泄漏风险
- 不可复现实验环节
- 对比不公平
- 指标不匹配研究目标
- 算力或实现复杂度明显不合理

输出 revise suggestions。
```

---

## 10. Communication with Other Modules

### Upstream
- 从 Synthesis Engine 接收 `ReviewReport`
- 从 Memory 读取项目历史与偏好

### Downstream
- 输出 `ExperimentPlan` 给 Experiment Engine
- 写入 artifact store
- 写入 `plan_addresses_gap` 关系到 Evidence Graph
- 向 Governance 发出 `plan_ready_for_approval`

---

## 11. Reuse-First Recommendations

- **模板化流程**：LangGraph subgraph 很适合
- **Flow 风格封装**：CrewAI Flows 可参考，但不要让 Crew 成为唯一编排方式
- **不要自己重造实验跟踪系统**：可预留对接 MLflow / W&B / 自定义 run store 的接口
