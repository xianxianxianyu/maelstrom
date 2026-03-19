# P3-04: Claim Extraction 节点

## 依赖
- P3-03（relevance_filtering — state["filtered_papers"]）
- P3-00（Claim, Evidence schema）
- P0-04（llm_client）

## 目的
从过滤后的论文中提取结构化 Claim 和 Evidence。每篇论文提取 problem / method / dataset / metric / main result / limitation 等字段，生成 Claim 对象并绑定原文 Evidence。

## 执行方法

### 1. 节点实现 — `src/maelstrom/graph/synthesis_nodes/claim_extraction.py`

```python
async def claim_extraction(state: dict) -> dict:
    """
    1. 将 filtered_papers 分批（每批 5 篇）
    2. 对每批调用 LLM，提取结构化 Claim
    3. 为每个 Claim 创建对应的 Evidence（原文片段）
    4. 写入 state["claims"] 和 state["evidences"]
    """
```

### 2. LLM Extraction Prompt

```text
你是文献结构化抽取器。
给定以下论文信息，请提取结构化 claim：

论文：{paper_title}
摘要：{paper_abstract}

请提取：
- problem: 研究问题
- method: 使用的方法
- dataset: 使用的数据集
- metric: 评估指标
- main_result: 主要结果
- limitation: 局限性

约束：
1. 仅依据提供内容
2. 不能凭空补全
3. 每个字段如果论文未提及则设为 null

输出 JSON：
{
  "claims": [
    {
      "claim_type": "method_effectiveness|dataset_finding|metric_comparison|limitation|assumption|negative_result",
      "text": "claim 原文描述",
      "extracted_fields": {"problem": "...", "method": "...", ...},
      "confidence": 0.0-1.0,
      "source_span": "abstract" 或具体位置描述
    }
  ]
}
```

### 3. 批处理策略
- 每批 5 篇论文（比 relevance_filtering 更小的批次，因为提取更复杂）
- 顺序处理（避免 LLM 并发过高）
- 单批超时 60s
- 每篇论文生成 1-3 个 Claim

### 4. Claim ID 和 Evidence ID 生成
- Claim ID: `clm-{uuid4_short}`
- Evidence ID: `evi-{uuid4_short}`
- 每个 Claim 自动创建一个对应的 Evidence，snippet 为 claim.text

### 5. SSE 增量推送
每批提取完成后推送 `claims_extracted` 事件，包含该批的 Claim 列表。

## 验收条件
- 每篇论文提取 1-3 个 Claim
- 每个 Claim 有对应的 Evidence
- Claim 包含 claim_type, text, extracted_fields, confidence
- Evidence 包含 source_span, snippet
- 批处理正确分批
- LLM 失败时该批论文跳过（不阻塞整体）
- state["claims"] 和 state["evidences"] 正确填充

## Unit Test
- `test_extraction_basic`: 3 篇论文 → 提取出 Claim 列表
- `test_extraction_fields`: Claim 包含 extracted_fields（problem/method/dataset/metric）
- `test_extraction_evidence_created`: 每个 Claim 有对应 Evidence
- `test_extraction_claim_types`: Claim.claim_type 是合法枚举值
- `test_extraction_batch`: 12 篇论文 → 分 3 批处理
- `test_extraction_llm_failure_skip`: 某批 LLM 失败 → 跳过该批，其余正常
- `test_extraction_empty_papers`: 无论文 → claims=[], evidences=[]
- `test_extraction_confidence_range`: 所有 Claim confidence 在 [0, 1]
