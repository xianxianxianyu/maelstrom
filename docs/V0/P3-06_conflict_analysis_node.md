# P3-06: Consensus / Conflict Analysis 节点

## 依赖
- P3-05（citation_binding — state["claims"], state["evidences"]）
- P3-00（ConsensusPoint, ConflictPoint schema）
- P0-04（llm_client）

## 目的
分析所有 Claim 之间的共识与冲突关系。找出哪些 Claim 相互支持（consensus），哪些存在直接矛盾（conflict），以及冲突的来源（数据集差异、指标差异、场景差异等）。

## 执行方法

### 1. 节点实现 — `src/maelstrom/graph/synthesis_nodes/conflict_analysis.py`

```python
async def conflict_analysis(state: dict) -> dict:
    """
    1. 将 claims 按 extracted_fields 中的 problem/method 分组（相似主题的 claims 才可能冲突）
    2. 对每组调用 LLM，分析共识与冲突
    3. 生成 ConsensusPoint[] 和 ConflictPoint[]
    4. 识别需要后续实验验证的冲突
    5. 写入 state["consensus_points"] 和 state["conflict_points"]
    """
```

### 2. LLM Conflict Analysis Prompt

```text
你是 Research Conflict Analyzer。
给定多个 claim 和对应 evidence，请判断：
- 哪些 claim 相互支持（consensus）
- 哪些 claim 存在直接冲突（conflict）
- 冲突是否来自数据集、指标、场景、假设差异
- 哪些冲突需要额外实验验证

Claims:
{claims_json}

输出 JSON：
{
  "consensus": [
    {"statement": "...", "supporting_claim_ids": ["clm-001", "clm-003"], "strength": "strong|moderate|weak"}
  ],
  "conflicts": [
    {"statement": "...", "claim_ids": ["clm-002", "clm-005"], "conflict_source": "dataset_difference|metric_difference|scenario_difference|assumption_difference", "requires_followup": true/false}
  ],
  "open_questions": ["..."]
}
```

### 3. 分组策略
- 按 claim 的 extracted_fields.problem 或 extracted_fields.method 做粗粒度分组
- 每组最多 15 个 claims（超过则拆分）
- 跨组不做冲突分析（不同 problem 的 claims 不太可能冲突）

### 4. SSE 增量推送
发现冲突时推送 `conflict_found` 事件。

## 验收条件
- 相互支持的 claims → ConsensusPoint（含 strength）
- 矛盾的 claims → ConflictPoint（含 conflict_source）
- 需要后续验证的冲突标记 requires_followup = true
- open_questions 列表生成
- 按 problem/method 正确分组
- LLM 失败时返回空列表（不阻塞）

## Unit Test
- `test_consensus_detected`: 2 个支持同一结论的 claims → ConsensusPoint
- `test_conflict_detected`: 2 个矛盾 claims → ConflictPoint
- `test_conflict_source_identified`: ConflictPoint 包含 conflict_source
- `test_requires_followup`: 某些冲突标记 requires_followup = true
- `test_open_questions_generated`: 输出包含 open_questions
- `test_grouping_by_problem`: claims 按 problem 分组
- `test_llm_failure_empty`: LLM 失败 → consensus=[], conflicts=[]
- `test_empty_claims`: 无 claims → 空结果
