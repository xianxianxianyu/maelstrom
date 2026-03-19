# P1-12: Gap Engine SSE 进度推送

## 依赖
- P1-11（Gap Engine API endpoints）

## 目的
实现 Gap Engine 运行过程的 SSE 流式进度推送，让前端实时展示工作流执行进度和中间结果。

## 执行方法
1. 在 `src/maelstrom/api/gap.py` 中添加路由：
   - `GET /api/gap/run/{run_id}/stream` — SSE 流式推送
2. SSE 事件类型实现：
   - `step_start`: `{step: str, index: int}` — 节点开始执行
   - `step_complete`: `{step: str, summary: str}` — 节点完成，附摘要
   - `papers_found`: `{count: int, papers: PaperRecord[], sources: SourceStatus[]}` — 检索+去重完成，**携带完整论文列表**，前端可立即渲染 PaperList 而无需额外请求
   - `gap_found`: `{gap: GapItem}` — 发现一个 Gap（增量推送，完整 GapItem 对象）
   - `matrix_ready`: `{coverage_matrix: dict, summary: {tasks: int, methods: int, datasets: int, empty_cells_pct: float}}` — 覆盖矩阵构建完成，携带完整矩阵数据
   - `result`: `{gaps: GapItem[], candidates: TopicCandidate[]}` — 最终结果（完整对象，非 ID 引用）
   - `error`: `{message: str, step: str}` — 错误信息
3. 实现方式：
   - LangGraph `astream_events` API 监听节点级事件
   - 转换为 SSE 事件格式
   - 使用 `sse-starlette` 的 `EventSourceResponse`
4. 连接管理：客户端断开时清理资源

## 验收条件
- SSE 连接建立后实时推送节点进度
- 8 个节点各推送 step_start + step_complete
- normalize_dedup 完成后推送 papers_found（含完整 PaperRecord[]）
- coverage_matrix 完成后推送 matrix_ready（含完整矩阵 dict）
- gap_hypothesis 每发现一个 Gap 推送 gap_found（含完整 GapItem）
- 最终推送 result 事件（含完整 GapItem[] 和 TopicCandidate[]）
- 错误时推送 error 事件
- 客户端断开后资源正确清理

## Unit Test
- `test_sse_connection`: 验证 SSE 连接建立成功
- `test_sse_step_events`: mock 图执行，验证收到 step_start/step_complete 事件
- `test_sse_papers_found`: 验证收到 papers_found 事件，payload 含完整 PaperRecord[]（非仅 count）
- `test_sse_matrix_ready`: 验证收到 matrix_ready 事件，payload 含完整 coverage_matrix dict
- `test_sse_gap_found`: 验证 Gap 发现时收到增量 gap_found 事件，payload 含完整 GapItem
- `test_sse_result`: 验证最终收到 result 事件，包含完整 gaps 和 candidates 对象
- `test_sse_error`: 图执行出错时收到 error 事件
- `test_sse_event_order`: 验证事件按正确顺序推送（step_start/complete 交替 → papers_found → matrix_ready → gap_found* → result）
- `test_sse_invalid_run_id`: 不存在的 run_id 返回 404
