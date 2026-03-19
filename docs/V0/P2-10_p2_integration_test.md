# P2-10: P2 集成测试

## 依赖
- P2-00 ~ P2-09（全部 P2 组件）

## 目的
端到端验证 Phase Router 统一入口的完整流程：用户输入 → 意图分类 → 路由 → 目标 engine 执行 → SSE 流式返回。覆盖所有意图类型和反问协议。

## 测试环境
- 使用 `pytest` + `httpx.AsyncClient` 测试 FastAPI app
- LLM 调用全部 mock（关键词分类器不需要 LLM，LLM fallback 用 mock）
- SQLite 使用内存数据库 `:memory:`
- paper-qa 使用 mock（返回固定回答）
- 四源检索使用 mock（返回固定论文）

## 测试用例

### E2E-01: Gap Discovery 全流程
```
1. 创建 session
2. POST /api/router/input/stream {"session_id": "...", "user_input": "帮我分析 NLP 领域的研究空白"}
3. 验证 SSE 事件序列：
   - route_resolved (intent=gap_discovery)
   - step_start (topic_intake)
   - step_complete (topic_intake)
   - ... (gap engine 各步骤)
   - result
   - __done__
4. 验证 evidence_memory 中有 ingest 的论文和 gap
5. 验证 session.current_phase = "ideation"
6. 验证 chat_messages 中有 intent="gap_discovery" 记录
```

### E2E-02: QA Chat 全流程
```
1. 创建 session
2. POST /api/router/input/stream {"session_id": "...", "user_input": "这篇论文的方法是什么？"}
3. 验证 SSE 事件序列：
   - route_resolved (intent=qa_chat)
   - chat_token (多个)
   - chat_done
   - __done__
```

### E2E-03: 反问 → 解决 全流程
```
1. 创建 session
2. POST /api/router/input/stream {"user_input": "transformer"}  (模糊输入)
3. 验证 SSE 事件：
   - route_resolved (intent=clarification_needed)
   - clarification (包含 options)
   - __done__
4. POST /api/chat/clarify {"request_id": "...", "option_index": 0}
5. 验证返回 RouterResponse，正确路由到选中的意图
```

### E2E-04: Gap Followup 增强
```
1. 创建 session + 执行一次 gap run（mock）
2. 验证 evidence_memory 有数据
3. POST /api/router/input/stream {"user_input": "第一个 gap 能展开说说吗"}
4. 验证 SSE 事件：
   - route_resolved (intent=gap_followup)
   - chat_token (回答中包含 gap 上下文)
   - chat_done
   - __done__
```

### E2E-05: 降级场景
```
1. 创建 session，不配置 LLM
2. POST /api/router/input/stream {"user_input": "分析研究空白"}
   - 关键词命中 gap_discovery → 尝试启动 gap engine → LLM 未配置 → error 事件
3. 验证 error 事件包含 "请先配置 LLM"
```

### E2E-06: 向后兼容
```
1. 直接调用 POST /api/chat/ask → 仍正常工作
2. 直接调用 POST /api/gap/run → 仍正常工作
3. 新旧端点不互相干扰
```

### E2E-07: Session Phase 追踪
```
1. 创建 session → current_phase = "ideation"
2. 执行 gap_discovery 路由 → current_phase 仍为 "ideation"
3. GET /api/sessions/{id} → 响应包含 current_phase
```

## 验收条件
- 7 个 E2E 测试全部通过
- 所有 SSE 流正确以 `__done__` 结束
- 无资源泄漏（SSE 连接正确关闭）
- mock 环境下全流程 < 5s 完成
- 测试可在 CI 中无外部依赖运行

## 文件位置
- `tests/integration/test_p2_10_e2e_router.py`
