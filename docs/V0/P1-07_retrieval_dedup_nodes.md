# P1-07: paper_retrieval + normalize_dedup 节点

## 依赖
- P1-05（Gap Engine 图定义）
- P1-04（PaperRetriever）

## 目的
实现 Gap Engine 的论文检索节点和跨源去重节点。

**职责分层**（与 P1-04 PaperRetriever 的边界）：
- PaperRetriever（P1-04）：并行调度四源 + 调用各 adapter 的 `normalize()`（源内格式转换）→ 返回已归一化但可能含跨源重复的 `PaperRecord[]`
- `paper_retrieval` 节点：编排层，遍历 expanded_queries 调用 PaperRetriever，合并多查询结果，写入 state
- `normalize_dedup` 节点：**仅做跨源去重**（DOI → S2 ID → 标题模糊匹配），输入已经是 PaperRecord[]，无需再做格式归一化

这样 checkpoint 落在 paper_retrieval 和 normalize_dedup 之间，可以重试去重而不重新检索。

## 执行方法
1. 在 `src/maelstrom/graph/nodes/paper_retrieval.py` 中实现：
   - 遍历 state.expanded_queries，调用 PaperRetriever.search_with_fallback
   - 合并所有查询的检索结果（PaperRecord[] 已由 adapter normalize 过）
   - 将 raw_papers 和 search_result（各源状态）写入 state
   - 更新 current_step
2. 在 `src/maelstrom/graph/nodes/normalize_dedup.py` 中实现：
   - 输入：state.raw_papers（已归一化的 PaperRecord[]，可能含跨源重复）
   - **跨源去重**（按优先级）：
     - DOI 精确匹配
     - Semantic Scholar ID / Corpus ID 匹配
     - 标题模糊匹配（Levenshtein ≥ 0.92 且首作者姓氏一致）
   - 合并重复记录的 external_ids，保留元数据最丰富的记录
   - 去重后的 papers 写入 state.papers
   - 更新 current_step
3. 检索失败处理：全部查询均无结果时设置 error，触发 Edge 路由到 error_end

## 验收条件
- paper_retrieval 对每个 expanded_query 调用 PaperRetriever
- 多查询结果正确合并
- search_result 包含各源状态信息
- normalize_dedup 输入为已归一化的 PaperRecord[]（不再重复做格式转换）
- normalize_dedup 去重后无跨源重复论文
- 去重时 external_ids 正确合并
- 全部检索失败时 error 字段被设置

## Unit Test
- `test_retrieval_calls_all_queries`: mock PaperRetriever，验证每个 expanded_query 都被调用
- `test_retrieval_merges_results`: 多查询返回不同论文，验证合并
- `test_retrieval_search_result`: 验证 search_result 包含 source_statuses
- `test_retrieval_all_fail`: 所有查询失败，验证 error 设置
- `test_dedup_doi`: 两条同 DOI 记录去重为一条
- `test_dedup_s2_id`: 两条同 S2 ID 记录去重为一条
- `test_dedup_title_fuzzy`: 标题相似度 ≥ 0.92 且首作者一致时去重
- `test_dedup_no_false_positive`: 标题相似但首作者不同时不去重
- `test_dedup_merge_external_ids`: 去重时 external_ids 合并（两源 ID 都保留）
- `test_dedup_keeps_richest`: 去重时保留元数据最丰富的记录（字段非空数最多）
- `test_dedup_input_already_normalized`: 验证 normalize_dedup 不修改已归一化字段（title/date 格式不变）
