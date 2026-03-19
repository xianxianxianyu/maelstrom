# P3-05: Citation Binding 节点

## 依赖
- P3-04（claim_extraction — state["claims"], state["evidences"]）
- P3-00（Claim, Evidence schema）

## 目的
将 Claim 与原文 Evidence 做精确绑定：验证每个 Claim 的 source_span 是否可追溯到论文原文，补充缺失的 span 信息，标记无法追溯的 Claim 降低其 confidence。

## 设计决策
V0 阶段论文内容仅有 abstract，无全文 PDF 解析。因此 Citation Binding 主要做：
1. 验证 Claim 文本是否可在 abstract 中找到支撑
2. 用 LLM 做 claim-abstract 对齐评分
3. 无法对齐的 Claim 标记 `source_span = "unverified"` 并降低 confidence

## 执行方法

### 1. 节点实现 — `src/maelstrom/graph/synthesis_nodes/citation_binding.py`

```python
async def citation_binding(state: dict) -> dict:
    """
    1. 遍历 claims，按 paper_id 分组
    2. 对每组调用 LLM，验证 claim 是否有 abstract 支撑
    3. 有支撑 → 更新 evidence.source_span 为具体位置
    4. 无支撑 → evidence.source_span = "unverified"，claim.confidence *= 0.6
    5. 更新 state["claims"] 和 state["evidences"]
    """
```

### 2. LLM 对齐 Prompt

```text
你是 Citation Alignment Checker。
给定论文摘要和从中提取的 claim，请验证 claim 是否有摘要支撑。

论文标题：{title}
摘要：{abstract}

Claims:
{claims_json}

对每个 claim 输出：
[{
  "claim_id": "...",
  "aligned": true/false,
  "source_span": "abstract, sentence N" 或 "unverified",
  "alignment_score": 0.0-1.0
}]
```

### 3. 批处理
- 按 paper_id 分组，每组一次 LLM 调用
- 单次超时 30s
- 失败时保留原始 claim 不修改

## 验收条件
- 有摘要支撑的 Claim → source_span 更新为具体位置
- 无支撑的 Claim → source_span = "unverified"，confidence 降低
- Evidence 对象同步更新
- LLM 失败时 Claim 保持不变（不报错）
- 按 paper_id 正确分组

## Unit Test
- `test_binding_aligned`: claim 有摘要支撑 → source_span 更新
- `test_binding_unverified`: claim 无支撑 → source_span = "unverified"，confidence 降低
- `test_binding_confidence_reduction`: unverified claim confidence *= 0.6
- `test_binding_groups_by_paper`: 多篇论文的 claims 按 paper_id 分组
- `test_binding_llm_failure_preserves`: LLM 失败 → claims 不变
- `test_binding_empty_claims`: 无 claims → 直接返回
