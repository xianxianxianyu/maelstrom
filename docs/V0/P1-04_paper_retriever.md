# P1-04: PaperRetriever 统一层

## 依赖
- P1-00（ArxivAdapter）
- P1-01（SemanticScholarAdapter）
- P1-02（OpenAlexAdapter）
- P1-03（OpenReviewAdapter）

## 目的
实现统一论文检索入口，并行调用四源适配器，每源调用各自 adapter 的 `normalize()` 将原始结果转为 PaperRecord，汇总后返回。**不做跨源去重**——跨源去重由下游 LangGraph `normalize_dedup` 节点负责（见 P1-07），以保持职责单一并允许 checkpoint 在检索与去重之间落点。

## 执行方法
1. 在 `src/maelstrom/services/paper_retriever.py` 中实现 `PaperRetriever`：
   - `adapters: list[BaseAdapter]` — 注入四个适配器实例
   - `async search(query: str, max_results: int = 50) -> list[PaperRecord]` — 并行调用四源，每源内部调用 `adapter.search()` + `adapter.normalize()`，合并返回（可能含跨源重复）
   - `async search_with_fallback(query: str, max_results: int = 50) -> SearchResult` — 同上 + 降级策略 + 各源状态
2. 并行调用：`asyncio.gather(*tasks, return_exceptions=True)`，per-source timeout 10s
3. **职责边界**：
   - PaperRetriever 负责：并行调度、per-source normalize（委托给 adapter）、降级、汇总
   - PaperRetriever **不**负责：跨源去重、标题模糊匹配、external_ids 合并（这些属于 P1-07 normalize_dedup 节点）
4. 降级策略：
   - 某源超时/错误 → 记录 warning，返回其余源结果
   - 仅一源成功 → 返回结果 + 标记 is_degraded=True
   - 全部失败 → 返回错误
5. 返回 `SearchResult`（papers + source_statuses + is_degraded）

## 验收条件
- 四源并行调用，总延迟接近最慢单源（非四源之和）
- 返回的 papers 已经过各 adapter normalize（字段完整），但**可能含跨源重复**
- 降级时返回可用源结果 + 各源状态
- 全部失败时返回明确错误
- source_statuses 包含每源的 status/count/latency_ms/error_msg

## Unit Test
- `test_parallel_search`: mock 四源，验证并行调用（总耗时 ≈ 最慢单源）
- `test_returns_all_sources`: 两源返回同 DOI 论文，验证 PaperRetriever **不去重**，两条都返回
- `test_per_adapter_normalize`: 验证每源结果经过 adapter.normalize()，PaperRecord 字段完整
- `test_fallback_one_source_fails`: 一源超时，验证其余三源结果正常返回
- `test_fallback_degraded`: 仅一源成功，验证 is_degraded=True
- `test_fallback_all_fail`: 全部失败，验证返回错误
- `test_source_statuses`: 验证每源 SourceStatus 字段正确
- `test_per_source_timeout`: 单源超过 10s 时标记该源 status=timeout，不阻塞其余源
