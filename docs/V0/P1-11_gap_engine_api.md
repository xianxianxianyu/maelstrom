# P1-11: Gap Engine API endpoints

## 依赖
- P1-05 ~ P1-10（Gap Engine 所有节点）
- P0-04（会话管理 API）

## 目的
实现 Gap Engine 的 REST API，允许前端启动 Gap Engine 工作流、查询运行状态和获取最终结果。

## 执行方法
1. 在 `src/maelstrom/api/gap.py` 中实现路由：
   - `POST /api/gap/run` — 启动 Gap Engine（传入 {topic, session_id}），后台异步执行，返回 run_id
   - `GET /api/gap/run/{run_id}/status` — 查询运行状态（current_step, status）
   - `GET /api/gap/run/{run_id}/result` — 获取完整结果：**ranked_gaps（完整 GapItem[]）+ topic_candidates（完整 TopicCandidate[]）+ papers（完整 PaperRecord[]）+ coverage_matrix（完整 dict）+ search_result（各源状态）**
   - `GET /api/gap/run/{run_id}/papers` — 子资源端点，仅返回该次运行检索到的完整论文列表（支持分页 ?offset=&limit=）
   - `GET /api/gap/run/{run_id}/matrix` — 子资源端点，仅返回完整覆盖矩阵
2. 在 `src/maelstrom/services/gap_service.py` 中封装：
   - 启动 LangGraph Gap Engine 图执行（异步 background task）
   - 从内存态读取当前 LLMConfig 注入 State
   - 运行状态写入 SQLite gap_runs 表
   - **检索到的论文写入 SQLite run_papers 表**（normalize_dedup 完成后批量写入）
   - 结果（gaps, candidates, matrix）写入 SQLite artifacts 表
3. 运行状态管理：
   - pending → running → completed / failed
   - 每个节点完成时更新 current_step
4. 错误处理：session 不存在 → 404，LLM 未配置 → 400，运行中异常 → 500 + error 详情

> **设计决策**：result 端点返回完整对象（非仅 ID 引用），前端详情页可一次请求获取所有渲染数据。论文列表可能较大（~50 条），提供独立 `/papers` 子资源端点支持分页，避免 result 响应过大时的替代方案。

## 验收条件
- POST /api/gap/run 返回 202 + run_id
- GET status 返回当前步骤和状态
- GET result 在完成后返回完整结果（papers[] + coverage_matrix + ranked_gaps[] + topic_candidates[] + search_result）
- GET result 在运行中返回 409（尚未完成）
- GET /papers 返回完整 PaperRecord 列表，支持分页
- GET /matrix 返回完整覆盖矩阵 dict
- 运行记录和论文持久化到 SQLite（gap_runs + run_papers）
- 无效 session_id 返回 404

## Unit Test
- `test_start_gap_run`: POST 启动，验证返回 202 + run_id
- `test_start_invalid_session`: 不存在的 session_id 返回 404
- `test_start_no_llm_config`: 未配置 LLM 时返回 400
- `test_get_status_running`: 运行中 GET status 返回 running + current_step
- `test_get_status_completed`: 完成后 GET status 返回 completed
- `test_get_result_completed`: 完成后 GET result 返回完整数据（papers, matrix, gaps, candidates, search_result）
- `test_get_result_not_ready`: 运行中 GET result 返回 409
- `test_get_papers_endpoint`: GET /papers 返回 PaperRecord 列表，验证分页参数生效
- `test_get_matrix_endpoint`: GET /matrix 返回完整覆盖矩阵 dict
- `test_run_persisted`: 验证 gap_runs 表有记录
- `test_papers_persisted`: 验证 run_papers 表有记录且数量与检索结果一致
