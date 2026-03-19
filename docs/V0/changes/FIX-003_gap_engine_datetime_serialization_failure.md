# FIX-003: Gap Engine 在 `papers_found` 事件阶段因 `datetime` 无法 JSON 序列化而中断

## 依赖
- P1-04（Paper Retriever）
- P1-07（Retrieval + Dedup Nodes）
- P1-11（Gap Engine API endpoints）
- P1-12（Gap Engine SSE 进度推送）
- P1-13（Gap Engine 前端页面）

## 目的
归档一次 Gap Engine 运行期故障：流程在前半段已成功完成检索，但在向前端推送论文列表时因 `datetime` 对象未完成 JSON 序列化而中断，导致后续 Coverage Matrix、Gap Hypothesis、Gap Critic、Ranking 均未继续执行。

## 执行方法
1. 在 Gap Engine 页面输入自然语言主题，例如“给我 agentic 的五个 topic”
2. 正常启动 run，前端进度依次显示：
   - `Topic Intake` 成功
   - `Query Expansion` 成功
   - `Paper Retrieval` 成功
   - `Deduplication` 进入中断态
3. 前端未进入 `Coverage Matrix / Gap Hypothesis / Gap Critic / Ranking`
4. 后端日志出现以下核心错误：

```text
Gap run <run_id> failed: Object of type datetime is not JSON serializable
Traceback (most recent call last):
  ...
  File "src/maelstrom/services/gap_service.py", line 146, in _execute_run
    _emit(run_id, "papers_found", {
  File "src/maelstrom/services/gap_service.py", line 83, in _emit
    q.put_nowait({"event": event, "data": json.dumps(data)})
  ...
TypeError: Object of type datetime is not JSON serializable
```

## 问题描述
- 该问题发生在 Gap Engine 工作流已经完成检索并准备向前端发送论文列表时
- 前端看到的表象是进度停在检索完成后的早期阶段，后续步骤均未执行
- 报错由后端抛出，不是前端渲染错误
- 该问题与用户输入的 topic 文本内容无直接关系，只要检索结果中包含带时间字段的论文对象，就可能触发

## 触发条件
- `paper_retrieval` 节点从多个 adapter 获取论文并返回 `PaperRecord`
- `PaperRecord` 含有 `retrieved_at: datetime`
- 这些对象在进入工作流 state 或 SSE 事件前，没有被转换为 JSON-safe 结构
- `_emit()` 在推送 `papers_found` 事件时直接执行 `json.dumps(data)`，从而触发序列化异常

## 定位结果
1. `PaperRecord` schema 明确定义了 `retrieved_at` 为 `datetime`
2. `paper_retrieval` 节点将 `PaperRecord` 使用默认 `model_dump()` 输出为 dict
3. 默认 `model_dump()` 保留 Python 原生 `datetime`，并不会自动变成 ISO 字符串
4. `gap_service._emit()` 默认假设传入数据已经可被 `json.dumps()` 直接处理
5. 当 `papers_found` 事件携带包含 `retrieved_at` 的论文列表时，序列化立即失败

## 错误链路
1. `PaperRetriever` 返回 `PaperRecord`
2. `paper_retrieval` 节点将 `PaperRecord` 转成普通 dict
3. `normalize_dedup` 之后，`gap_service._execute_run()` 准备发出 `papers_found`
4. `_emit()` 调用 `json.dumps(data)`
5. `data["papers"][*]["retrieved_at"]` 中存在 `datetime`
6. `json.dumps()` 抛出 `TypeError`
7. 当前 run 被标记为 failed，后续步骤不再继续

## 非根因说明
- 日志中出现的 `Semantic Scholar` 429 不是这次 run 失败的直接根因
- 当前检索层对单个 adapter 的超时/失败设计为降级继续
- 本次 run 的致命错误是序列化异常，而不是检索源限流

## 影响范围
- Gap Engine SSE 事件流
- Gap run 的论文结果持久化
- 依赖论文列表继续执行的后续节点展示
- 前端进度条和结果区域的一致性

## 涉及文件
| 文件 | 作用 |
|------|------|
| `src/maelstrom/schemas/paper.py` | 定义 `PaperRecord.retrieved_at: datetime` |
| `src/maelstrom/graph/nodes/paper_retrieval.py` | 将 `PaperRecord` 写入 state |
| `src/maelstrom/graph/nodes/normalize_dedup.py` | 后续节点读取论文列表的中间边界 |
| `src/maelstrom/services/gap_service.py` | 负责 SSE 事件发送、run 持久化与错误抛出处 |
| `src/maelstrom/services/paper_retriever.py` | 汇总多源检索结果并返回 `PaperRecord` |
| `src/maelstrom/adapters/arxiv_adapter.py` | 生成带 `retrieved_at` 的论文对象 |
| `src/maelstrom/adapters/s2_adapter.py` | 生成带 `retrieved_at` 的论文对象 |
| `src/maelstrom/adapters/openalex_adapter.py` | 生成带 `retrieved_at` 的论文对象 |
| `src/maelstrom/adapters/openreview_adapter.py` | 生成带 `retrieved_at` 的论文对象 |
| `frontend/src/hooks/useGapStream.ts` | 前端消费 `papers_found` 事件的入口 |
| `frontend/src/app/gap/page.tsx` | 前端展示 Gap Engine 运行状态与结果 |

## 验收条件
- 文档明确记录该故障发生在 `papers_found` 事件阶段，而非检索阶段本身
- 文档明确区分直接根因与 `s2 429` 之类的非根因日志
- 文档能够从 schema、节点、服务三层说明 `datetime` 如何进入 `json.dumps()`
- 文档包含足够精确的涉及文件索引，便于后续实现与测试时快速定位
