# P0-12: P0 前后端联调 + 集成测试

## 依赖
- P0-07（QA Chat API + SSE 流式）
- P0-11（PDF 上传前端组件）

## 目的
验证 Phase 0 所有组件端到端协作正确，确保 QA Chat 完整流程（上传 PDF → 提问 → 流式回答 + 引用）可正常运行。

## 执行方法
1. 端到端测试场景：
   - 场景 1：LLM 配置 → 前端配置 LLM → 后端存储 → 验证配置生效
   - 场景 2：PDF 上传 → 前端上传 → 后端存储 + 索引 → 验证文档列表
   - 场景 3：QA Chat → 上传 PDF → 提问 → SSE 流式回答 → 引用可追溯
   - 场景 4：会话管理 → 创建会话 → 在会话内操作 → 删除会话 → 数据清理
2. SSE 协议联调：
   - 验证前端 EventSource 正确解析后端 SSE 事件
   - 验证 chat_token / chat_done / error 事件格式一致
   - 验证连接断开和重连行为
3. 错误场景测试：
   - LLM 配置无效（错误 API key）→ 前端显示错误
   - 上传非 PDF → 前端显示拒绝
   - 无索引文档时提问 → 前端显示提示
4. 使用 pytest + httpx 做后端集成测试
5. 使用 Playwright 或 Cypress 做前端 E2E 测试（可选）

## 验收条件
- 完整 QA Chat 流程端到端跑通：配置 LLM → 上传 PDF → 提问 → 收到带引用的流式回答
- SSE 事件前后端格式一致，无解析错误
- 会话创建/删除正常，数据级联清理
- 错误场景有明确的用户提示
- 所有集成测试通过

## Unit Test
- `test_e2e_qa_chat_flow`: 完整流程：创建会话 → 配置 LLM → 上传 PDF → 提问 → 验证流式回答
- `test_e2e_llm_config_roundtrip`: 前端配置 → 后端存储 → 前端读取，验证一致
- `test_e2e_session_lifecycle`: 创建 → 上传文档 → 提问 → 删除 → 验证清理
- `test_e2e_sse_format`: 验证 SSE 事件 event/data 字段格式正确
- `test_e2e_error_invalid_key`: 配置无效 API key 后提问，验证错误响应
- `test_e2e_no_docs_warning`: 无索引文档时提问，验证提示信息
