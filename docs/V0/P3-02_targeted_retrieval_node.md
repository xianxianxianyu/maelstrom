# P3-02: Targeted Retrieval 节点

## 依赖
- P3-01（SynthesisEngineGraph + SynthesisRunState）
- P2-02（EvidenceMemory — search / search_by_source_id）
- P1-04（PaperRetriever — 四源并行检索）

## 目的
实现 Synthesis Engine 第一个节点：针对选定的 gap/topic 做精准文献检索。采用 EvidenceMemory 已有论文 + 增量检索补充的策略。

## 执行方法

### 1. 节点实现 — `src/maelstrom/graph/synthesis_nodes/targeted_retrieval.py`

```python
async def targeted_retrieval(state: dict) -> dict:
    """
    1. 从 EvidenceMemory 读取已有论文（基于 session_id + gap 关键词）
    2. 用 LLM 生成 2-3 个精准检索 query（比 Gap Engine 的 query_expansion 更聚焦）
    3. 调用 PaperRetriever 做增量检索
    4. 合并去重（已有 + 新检索）
    5. 写入 state["targeted_papers"]
    """
```

### 2. 精准 Query 生成

与 Gap Engine 的 query_expansion 不同，这里的 query 更聚焦：
- 输入：gap title + gap summary + gap_type（或 topic）
- LLM prompt：生成 2-3 个针对该 gap 的精准检索 query，侧重 method/dataset/limitation
- 输出：`list[str]`

### 3. EvidenceMemory 复用

```python
# 1. 从 EvidenceMemory 读取已有论文
mem = get_evidence_memory()
existing_hits = await mem.search(session_id, gap_title_or_topic, limit=20)
existing_paper_ids = {h.source_id for h in existing_hits if h.source_type == "paper"}

# 2. 增量检索
retriever = PaperRetriever()
for query in targeted_queries:
    result = await retriever.search_with_fallback(query, max_per_source=5)
    new_papers = [p for p in result.papers if p.paper_id not in existing_paper_ids]
    ...

# 3. 合并
all_papers = existing_papers + new_papers
```

### 4. 新论文写入 EvidenceMemory

增量检索到的新论文自动 ingest 到 EvidenceMemory，供后续节点和未来查询使用。

## 验收条件
- 从 EvidenceMemory 读取已有论文
- LLM 生成 2-3 个精准 query
- PaperRetriever 增量检索
- 已有 + 新论文合并去重
- 新论文写入 EvidenceMemory
- 无论文时 state["error"] 被设置
- state["targeted_papers"] 包含合并后的论文列表

## Unit Test
- `test_retrieval_from_evidence_memory`: EvidenceMemory 有论文 → 读取到 targeted_papers
- `test_retrieval_incremental`: EvidenceMemory 有 2 篇 + 检索到 3 篇新 → 合并 5 篇
- `test_retrieval_dedup`: 已有论文不重复出现
- `test_retrieval_new_papers_ingested`: 新论文写入 EvidenceMemory
- `test_retrieval_no_papers_error`: 无论文 → state["error"]
- `test_targeted_query_generation`: LLM 生成 2-3 个 query（mock）
- `test_retrieval_gap_input`: 输入 GapItem → 正确提取 gap 信息做检索
- `test_retrieval_topic_input`: 输入 topic 字符串 → 正确检索
