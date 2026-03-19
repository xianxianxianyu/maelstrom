# P1-13: Gap Engine 前端页面

## 依赖
- P0-08（Next.js 项目骨架）
- P1-12（Gap Engine SSE 进度推送）

## 目的
实现 Gap Engine 前端页面，包括主题输入、运行进度可视化、检索论文列表、覆盖矩阵展示和 Gap 结果列表。

## 执行方法
1. 创建组件：
   - `components/gap/TopicInput.tsx` — 主题输入表单（textarea + 提交按钮）
   - `components/gap/RunProgress.tsx` — 8 步工作流进度条（step 名称 + 状态图标 + 当前高亮）
   - `components/gap/PaperList.tsx` — 检索到的论文列表（title, authors, venue, year, source badge）
   - `components/gap/CoverageMatrix.tsx` — 覆盖矩阵展示（表格或简化热力图，tooltip 显示论文）
   - `components/gap/GapCard.tsx` — 单个 GapItem 卡片（title, summary, gap_type badges, scores 条形图, confidence）
   - `components/gap/GapList.tsx` — ranked GapItem 列表
   - `components/gap/TopicCandidateCard.tsx` — TopicCandidate 卡片（title, risk_summary, next_step）
2. 创建自定义 hook `hooks/useGapStream.ts`：
   - 封装 EventSource，监听 step_start/step_complete/papers_found/matrix_ready/gap_found/result/error
   - 返回 {steps, papers, matrix, gaps, candidates, status}
3. **数据来源契约**（解决前端数据无稳定来源问题）：
   - **运行中（实时流）**：SSE 事件携带完整对象——`papers_found` 含 PaperRecord[]，`matrix_ready` 含完整 coverage_matrix dict，`gap_found` 含完整 GapItem，`result` 含完整 GapItem[] + TopicCandidate[]。useGapStream hook 累积这些数据供组件渲染。
   - **详情页（持久化数据）**：`GET /api/gap/run/{run_id}/result` 返回完整 GapAnalysisResult（含 papers[], coverage_matrix, ranked_gaps[], topic_candidates[]）。论文列表较大时可用 `GET /api/gap/run/{run_id}/papers` 分页加载。
   - **不依赖** GapAnalysisResult 中的 summary 字段或 ID 引用来渲染 UI——所有展示数据均为完整对象。
4. 页面集成 `app/gap/page.tsx`：
   - 输入 topic → POST /api/gap/run → 获取 run_id → 连接 SSE
   - 实时更新进度条、论文列表、覆盖矩阵、Gap 列表
5. 运行详情页 `app/gap/[runId]/page.tsx`：
   - 从 result API 加载完整数据（论文 + 矩阵 + Gap + TopicCandidate）
   - 支持从会话列表或历史记录进入

## 验收条件
- 输入 topic 后启动运行，进度条实时更新
- 检索完成后论文列表显示
- Gap 发现时卡片增量出现
- 最终结果完整展示（ranked gaps + topic candidates）
- 覆盖矩阵可视化可读
- 错误时显示错误信息

## Unit Test
- `test_topic_input_submit`: 输入 topic 点击提交，验证 POST 请求
- `test_progress_bar_updates`: mock SSE，验证进度条随 step 事件更新
- `test_paper_list_renders`: mock 数据，验证论文列表正确渲染
- `test_gap_card_fields`: 验证 GapCard 显示 title/summary/scores
- `test_gap_list_order`: 验证 GapList 按评分降序排列
- `test_coverage_matrix_display`: mock 数据，验证矩阵表格渲染
- `test_topic_candidate_card`: 验证 TopicCandidateCard 字段显示
- `test_error_display`: SSE error 事件时显示错误信息
