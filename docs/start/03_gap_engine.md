# Gap Engine

## 1. Module Definition

Gap Engine 负责在研究生命周期最前段完成“选题发现”和“缺口论证”的第一轮粗筛。  
它输出的不是最终课题，而是一组 **候选研究缺口（GapItem）** 与 **候选课题（TopicCandidate）**，并附带支持证据。

---

## 2. Core Objectives

1. 识别当前主题下已被充分覆盖与未被充分覆盖的区域。
2. 分析 task / method / dataset / metric / deployment setting 的覆盖情况。
3. 生成高价值 gap hypotheses，并进行 evidence-backed scoring。
4. 输出供用户进入 Synthesis Engine 的候选方向。

---

## 3. Inputs / Outputs

### Inputs
- `topic`
- optional constraints（领域、时间窗、模态、应用场景）
- optional user preference memory

### Outputs
- `GapItem[]`
- `TopicCandidate[]`
- `GapReport`
- trace + evidence links

---

## 4. Recommended Pipeline

```mermaid
flowchart LR
  A["Topic Intake"] --> B["Query Expansion"]
  B --> C["Survey / Paper Retrieval"]
  C --> D["Metadata Normalize + Dedup"]
  D --> E["Coverage Matrix Builder"]
  E --> F["Gap Hypothesis Generator"]
  F --> G["Gap Critic / Scorer"]
  G --> H["Candidate Ranking"]
  H --> I["Human Review"]
```

---

## 5. Agent vs Non-Agent Boundary

### Use Agent
- Query expansion
- Gap hypothesis generation
- Gap critique / scoring explanation
- Multi-perspective opportunity ranking

### Do Not Use Agent
- paper metadata normalization
- deduplication
- clustering
- dataset / metric coverage counting
- ranking feature assembly

---

## 6. Internal Submodules

| Submodule | What it does | Recommended style |
|---|---|---|
| Query Expansion | 拆 topic、生成检索维度 | Planner / Retriever agent |
| Retrieval Adapter | 调搜索、论文 API、MCP resources | MCP + standard tools |
| Coverage Matrix Builder | 统计 task-method-dataset-metric 覆盖 | Programmatic skill |
| Gap Hypothesis Generator | 从 coverage 缺口生成候选问题 | Critic/Planner agent |
| Gap Scorer | 根据 novelty / feasibility / evidence 评分 | Skill + critic agent |
| Ranking & Packaging | 输出 `GapItem[]` 和报告 | Workflow + renderer |

---

## 7. Artifact Schema Suggestions

### `GapItem`
```json
{
  "gap_id": "gap-001",
  "title": "Lack of robust evaluation for mobile EEG artifact removal",
  "summary": "Current studies focus on lab settings and under-evaluate ambulatory noise conditions.",
  "gap_type": ["dataset", "evaluation", "deployment_setting"],
  "evidence_refs": ["evi-001", "evi-013"],
  "confidence": 0.77,
  "scores": {
    "novelty": 0.68,
    "feasibility": 0.74,
    "impact": 0.83
  }
}
```

### `TopicCandidate`
```json
{
  "candidate_id": "cand-001",
  "title": "EEG artifact removal under ambulatory real-world noise",
  "related_gap_ids": ["gap-001"],
  "recommended_next_step": "run Synthesis Engine",
  "risk_summary": "dataset curation may be hard"
}
```

---

## 8. Skills to Implement

### `coverage_analysis_skill`
输入：`PaperRecord[]`  
输出：task-method-dataset-metric coverage matrix

### `gap_scoring_skill`
输入：`GapItem draft + evidence refs`  
输出：score breakdown + ranking features

### `topic_cluster_skill`
输入：paper abstracts / keywords  
输出：clusters for topic map

---

## 9. Prompt Templates

### 9.1 Gap Hypothesis Prompt
```text
你是 Research Gap Finder。
请根据以下 coverage matrix、paper summaries 和 evidence snippets，
找出最值得进一步论证的研究缺口。

要求：
1. 缺口必须明确属于 task / method / dataset / metric / deployment / evaluation 中的一类或多类
2. 不允许空泛表述，如“仍需更多研究”
3. 每条 gap 必须绑定至少 2 个证据引用
4. 输出 JSON 数组

输出字段：
- title
- summary
- gap_type
- why_now
- evidence_refs
- possible_counterarguments
```

### 9.2 Gap Critic Prompt
```text
你是 Gap Critic。
请检查每个候选 gap 是否存在：
- 实际上已有大量工作覆盖
- 所谓缺口只是表述偏差
- 证据不足
- 工程不可行性被忽略

输出：
{
  "gap_id": "...",
  "verdict": "keep|revise|drop",
  "reasons": ["..."],
  "missing_evidence": ["..."]
}
```

---

## 10. Communication with Other Modules

### Upstream
- 从 Workspace 接收 topic / constraints
- 从 Memory 读取用户偏好与项目历史

### Downstream
- 向 Synthesis Engine 发 `GapItem` / `TopicCandidate`
- 向 Artifact Store 写 `GapReport`
- 向 Evidence Graph 写 gap-evidence 关系
- 向 Trace Bus 发 `gap_candidate_generated`, `gap_candidate_dropped` 事件

---

## 11. Reuse-First Recommendations

- **Retrieval / state / DAG**：优先 LangGraph + MCP
- **多 agent 对照实验**：可参考 AutoGen literature review 示例
- **不要自己造 group chat team runtime**：第一版不需要像 Magentic-One 那样全局 orchestrator
