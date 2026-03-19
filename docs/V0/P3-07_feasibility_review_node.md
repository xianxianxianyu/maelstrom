# P3-07: Feasibility Review 节点

## 依赖
- P3-06（conflict_analysis — state["consensus_points"], state["conflict_points"]）
- P3-00（FeasibilityMemo, FeasibilityVerdict schema）
- P0-04（llm_client）

## 目的
基于综述结果评估该研究方向的可行性，生成 FeasibilityMemo（verdict: advance / revise / reject）。V0 阶段为自动输出，不设 HITL 审批节点。

## 执行方法

### 1. 节点实现 — `src/maelstrom/graph/synthesis_nodes/feasibility_review.py`

```python
async def feasibility_review(state: dict) -> dict:
    """
    1. 汇总 claims, consensus, conflicts, open_questions
    2. 调用 LLM 做四维评估：
       - gap_validity: 缺口是否真实成立
       - existing_progress: 现有工作是否已接近解决
       - resource_assessment: 实验资源要求是否合理
       - 综合 verdict: advance / revise / reject
    3. 生成 FeasibilityMemo
    4. 写入 state["feasibility_memo"]
    """
```

### 2. LLM Feasibility Prompt

```text
你是课题可行性审查员。
请根据以下综述信息评估该研究方向的可行性。

研究方向：{topic}
研究缺口：{gap_summary}
共识点数量：{consensus_count}
冲突点数量：{conflict_count}
开放问题：{open_questions}

关键 Claims 摘要：
{top_claims_summary}

请评估：
1. gap_validity: 该方向的真实缺口是否成立（1-2 句话）
2. existing_progress: 现有工作是否已接近解决（1-2 句话）
3. resource_assessment: 实验资源要求是否合理（1-2 句话）
4. verdict: advance（值得立项）/ revise（需调整方向）/ reject（不建议继续）
5. reasoning: 综合理由（2-3 句话）
6. confidence: 0.0-1.0

输出 JSON：
{
  "gap_validity": "...",
  "existing_progress": "...",
  "resource_assessment": "...",
  "verdict": "advance|revise|reject",
  "reasoning": "...",
  "confidence": 0.0-1.0
}
```

### 3. 降级策略
- LLM 失败时生成默认 FeasibilityMemo：verdict = "revise"，reasoning = "自动评估失败，建议人工审查"
- confidence 设为 0.0

## 验收条件
- FeasibilityMemo 包含四维评估 + verdict + reasoning
- verdict 是合法枚举值（advance / revise / reject）
- confidence 在 [0, 1] 范围
- LLM 失败时降级为默认 memo
- state["feasibility_memo"] 正确填充

## Unit Test
- `test_feasibility_advance`: 共识多冲突少 → verdict = "advance"（mock LLM）
- `test_feasibility_revise`: 冲突多 → verdict = "revise"（mock LLM）
- `test_feasibility_reject`: 缺口不成立 → verdict = "reject"（mock LLM）
- `test_feasibility_four_dimensions`: memo 包含 gap_validity, existing_progress, resource_assessment, reasoning
- `test_feasibility_confidence_range`: confidence 在 [0, 1]
- `test_feasibility_llm_failure`: LLM 失败 → 默认 revise memo
- `test_feasibility_empty_input`: 无 claims/consensus → 仍生成 memo
