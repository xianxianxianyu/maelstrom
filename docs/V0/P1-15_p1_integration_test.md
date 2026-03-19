# P1-15: P1 端到端集成测试

## 依赖
- P1-14（Gap → QA Chat 联动）

## 目的
验证 Phase 1 所有组件端到端协作正确，确保完整 Gap Engine 流程（输入 topic → 四源检索 → 覆盖矩阵 → Gap 生成 → 评审排序 → 结果展示 → QA Chat 联动）可正常运行。

## 执行方法
1. 端到端测试场景：
   - 场景 1：完整 Gap Engine 流程 — 输入 topic → 检索 → 矩阵 → Gap → 排序 → 输出 ranked_gaps + topic_candidates
   - 场景 2：降级检索 — 模拟某源不可用，验证其余源正常返回 + is_degraded 标记
   - 场景 3：SSE 进度推送 — 验证 8 个节点的 step_start/step_complete 事件完整推送
   - 场景 4：Gap → QA Chat 联动 — Gap 完成后论文共享到 QA，追问按钮跳转正确
   - 场景 5：错误恢复 — LLM 调用失败后从 checkpoint 恢复
2. 后端集成测试：
   - 使用 pytest + httpx AsyncClient
   - mock 外部 API（四源 + LLM），验证内部流程
   - 验证 SQLite 数据持久化（gap_runs, artifacts）
3. 前端 E2E 测试（可选）：
   - 使用 Playwright
   - 验证 TopicInput → RunProgress → GapList → 追问跳转
4. SSE 协议测试：
   - 验证事件类型和 payload 格式
   - 验证事件顺序（step_start → step_complete 交替，最终 result）

## 验收条件
- 完整 Gap Engine 流程端到端跑通（mock 外部依赖）
- 四源检索并行执行，降级策略生效
- SSE 事件完整且顺序正确
- Gap → QA Chat 论文共享和追问跳转正常
- 所有数据正确持久化到 SQLite
- 错误场景有明确处理（不崩溃、有提示）
- 所有集成测试通过

## Unit Test
- `test_e2e_gap_engine_full`: 完整流程：topic → ranked_gaps + topic_candidates，验证输出结构
- `test_e2e_search_degraded`: 模拟一源超时，验证其余源结果 + is_degraded=True
- `test_e2e_search_all_fail`: 模拟全部源失败，验证错误响应
- `test_e2e_sse_complete_flow`: 连接 SSE，验证收到所有 step 事件 + result 事件
- `test_e2e_gap_to_qa_share`: Gap 完成后验证论文已索引到 QA Chat
- `test_e2e_gap_to_qa_ask`: 共享后在 QA Chat 提问，验证可回答
- `test_e2e_checkpoint_recovery`: 模拟中间节点失败，从 checkpoint 恢复继续执行
- `test_e2e_result_persisted`: 验证 gap_runs 和 artifacts 表数据正确
- `test_e2e_concurrent_runs`: 同一 session 启动两次运行，验证互不干扰
