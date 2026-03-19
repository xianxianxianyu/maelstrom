# P3-03: Relevance Filtering 节点

## 依赖
- P3-02（targeted_retrieval — state["targeted_papers"]）
- P0-04（llm_client）

## 目的
过滤 targeted_retrieval 返回的论文，去掉与 gap/topic 不相关的噪声文献。采用 LLM 批量评分 + 阈值过滤的方式。

## 执行方法

### 1. 节点实现 — `src/maelstrom/graph/synthesis_nodes/relevance_filtering.py`

```python
async def relevance_filtering(state: dict) -> dict:
    """
    1. 将 targeted_papers 分批（每批 10 篇）
    2. 对每批调用 LLM，评估每篇论文与 gap/topic 的相关性（0-1 分）
    3. 过滤掉 relevance < 0.4 的论文
    4. 写入 state["filtered_papers"]
    """
```

### 2. LLM 评分 Prompt

```text
你是文献相关性评估器。
研究方向：{topic}
研究缺口：{gap_summary}

请评估以下论文与该研究方向的相关性（0.0-1.0）：
{papers_batch_json}

输出 JSON 数组：
[{"paper_id": "...", "relevance": 0.0-1.0, "reason": "..."}]
```

### 3. 批处理策略
- 每批 10 篇论文
- 并行调用 LLM（最多 3 个并发批次）
- 单批超时 30s，超时的论文默认保留（relevance=0.5）

### 4. 降级策略
- 如果 LLM 调用全部失败，保留所有论文（不过滤）
- 如果过滤后论文数 < 3，降低阈值到 0.2 重新过滤

## 验收条件
- 低相关性论文被过滤（relevance < 0.4）
- 高相关性论文保留
- 批处理正确分批
- LLM 失败时降级为全部保留
- 过滤后论文数 < 3 时降低阈值
- state["filtered_papers"] 包含过滤后的论文

## Unit Test
- `test_filter_removes_irrelevant`: 5 篇论文，2 篇 relevance < 0.4 → 过滤后 3 篇
- `test_filter_keeps_relevant`: 全部 relevance > 0.4 → 全部保留
- `test_filter_batch_processing`: 25 篇论文 → 分 3 批处理
- `test_filter_llm_failure_fallback`: LLM 失败 → 全部保留
- `test_filter_too_few_lowers_threshold`: 过滤后 < 3 篇 → 降低阈值重试
- `test_filter_empty_input`: 无论文 → state["filtered_papers"] = []
