# P3-12: P3 集成测试

## 依赖
- P3-00 ~ P3-11（全部 P3 组件）

## 目的
端到端验证 Synthesis Engine 完整流程：输入 gap/topic → 7 节点流水线 → ReviewReport + FeasibilityMemo 输出。覆盖双入口、SSE 流、Phase 联动、EvidenceMemory 回写。

## 测试环境
- pytest + httpx.AsyncClient
- LLM 全部 mock
- SQLite 内存数据库
- PaperRetriever mock

## 测试用例

### E2E-01: Topic 输入 → 完整 Synthesis 流程
```
1. 创建 session + 配置 LLM profile
2. POST /api/synthesis/run { session_id, topic: "Transformer for NER" }
3. 等待 run 完成
4. GET /api/synthesis/run/{id}/result
5. 验证：
   - ReviewReport 包含 claims, consensus, conflicts
   - FeasibilityMemo 包含 verdict
   - paper_count > 0
```

### E2E-02: Gap 输入 → Synthesis 流程
```
1. 创建 session + 执行 Gap Engine run（mock）
2. 从 gap 结果中取一个 gap_id
3. POST /api/synthesis/run { session_id, gap_id }
4. 等待完成
5. 验证 ReviewReport.source_gap_id == gap_id
```

### E2E-03: SSE 事件完整性
```
1. 启动 synthesis run
2. 订阅 SSE 流
3. 验证事件序列：
   - 7 个 step_start + 7 个 step_complete
   - claims_extracted 事件
   - result 事件
   - __done__ 事件
```

### E2E-04: Phase 联动
```
1. 创建 session → phase = ideation
2. 执行 synthesis run
3. 完成后 GET /api/sessions/{id} → phase = grounding
```

### E2E-05: EvidenceMemory 回写
```
1. 执行 synthesis run
2. 完成后查询 EvidenceMemory
3. 验证有 review / claim / feasibility 记录
4. 验证 claim 可通过 FTS 搜索到
```

### E2E-06: Router 集成
```
1. POST /api/router/input { user_input: "帮我做文献综述" }
2. 验证 response_type = "stream"
3. 验证 stream_url 包含 "/api/synthesis/"
4. 验证 intent = "synthesis"
```

### E2E-07: 向后兼容
```
1. 直接调用 POST /api/gap/run → 仍正常
2. 直接调用 POST /api/chat/ask → 仍正常
3. 直接调用 POST /api/router/input → 仍正常
```

### E2E-08: 检索失败降级
```
1. Mock PaperRetriever 返回空结果 + EvidenceMemory 也为空
2. POST /api/synthesis/run
3. 验证 run status = failed
4. 验证 error 信息包含 "No papers found"
```

## 验收条件
- 8 个 E2E 测试全部通过
- 所有 SSE 流以 `__done__` 结束
- mock 环境下全流程 < 10s
- 测试可在 CI 中无外部依赖运行

## 文件位置
- `tests/integration/test_p3_12_e2e_synthesis.py`
