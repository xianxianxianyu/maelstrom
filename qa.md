# Maelstrom QA V1 架构说明（Context-First）

> 本文档描述当前已落地的 QA V1 方案。
> 目标是让 QA 的底层从“临时会话缓存”升级为“标准化 QA Context 系统”。

---

## 1. 设计目标

QA V1 的核心目标是：

1. **Context 先行**：每次问答先进入上下文内核，再做意图识别与子任务执行。
2. **会话隔离**：每个 `session` 拥有独立存储空间（独立 SQLite 文件）。
3. **固定对话格式**：每个 `turn` 使用统一 schema，强制包含 `summary`、`tags`、`intent_tag`。
4. **可索引可判断**：支持按 query/tag/intent/entity 检索历史对话，用于 Stage1/Stage2 决策。
5. **subagent 可替换**：编排层只依赖 capability，不绑定具体 agent 实现。

---

## 2. 当前入口与接口

当前 QA V1 后端入口为：

- `POST /api/qa/v1/query`
- `POST /api/qa/v1/clarify/{thread_id}`
- `GET /api/qa/v1/sessions/{session_id}/turns`
- `GET /api/qa/v1/turns/{turn_id}?session_id=...`
- `GET /api/qa/v1/health`

应用已在 `backend/app/main.py` 注册 `qa_v1_route.router`。

---

## 3. 总体架构

```text
Client
  -> /api/qa/v1/query
    -> QAContextKernel
       1) create_session + append pending turn
       2) Stage1 (coarse intent + context selection)
       3) Stage2 (sub-problems + routing plan)
       4) Clarification Gate (if needed)
       5) SubagentRunner (capability-based execution)
       6) Enrichment (summary/tags/entities)
       7) commit turn + index update
  <- KernelResponse
```

澄清分支：

```text
clarification_pending
  -> /api/qa/v1/clarify/{thread_id}
    -> merge clarification
    -> rerun query pipeline
```

---

## 4. 关键模块与职责

### 4.1 Context Kernel

- 文件：`agent/qa_context_v1/kernel.py`
- 负责统一流程编排：ingest、stage1、stage2、clarification、subagent 执行、commit。

### 4.2 会话存储（SessionSQLiteStore）

- 文件：`agent/qa_context_v1/store.py`
- 每个 session 一个独立 DB：`data/qa_v1/sessions/{session_id}/context.db`
- 核心表：
  - `session_meta`
  - `turns`
  - `turn_tags`
  - `turn_entities`
  - `clarifications`
  - `artifacts`

### 4.3 索引器（QAContextIndexer）

- 文件：`agent/qa_context_v1/indexer.py`
- 基于 query 文本重叠与时序做候选上下文排序。

### 4.4 澄清管理器（ClarificationManager）

- 文件：`agent/qa_context_v1/clarification.py`
- 负责是否澄清判断（由 Stage2 触发）、创建线程、合并澄清答案。

### 4.5 对话增强器（TurnEnricher）

- 文件：`agent/qa_context_v1/enrichment.py`
- 负责生成 `summary`、`entities`、`tags`、`topic_tags`。

### 4.6 可插拔 subagent 编排层

- 文件：
  - `agent/qa_orchestration/contracts.py`
  - `agent/qa_orchestration/subagent_registry.py`
  - `agent/qa_orchestration/subagent_runner.py`
- 默认能力映射：
  - `context.retrieve` -> `retrieval-subagent`
  - `reasoning.synthesize` -> `reasoning-subagent`
  - `response.compose` -> `response-subagent`

---

## 5. 固定对话 Schema（V1）

核心对象：`DialogueTurn`（`schema_version = qa-turn-v1`）

必备字段：

- 身份与时序：`turn_id`, `session_id`, `created_at`, `updated_at`
- 输入输出：`user_query`, `assistant_answer`
- 可索引字段：`summary`, `tags`, `topic_tags`, `intent_tag`, `entities`
- 证据与引用：`referenced_docs`, `citations`
- 决策工件：`stage1_result`, `stage2_result`, `routing_plan`, `agent_runs`
- 状态与追踪：`status`, `trace_id`, `clarification_thread_id`, `error`

说明：`summary/tags/intent_tag` 在 V1 中是强制写入字段，不再可选。

---

## 6. Stage1 / Stage2（当前实现）

### Stage1（粗粒度）

- 输入：query + session 上下文候选
- 输出：`Stage1Result`
  - `coarse_intent`
  - `confidence`
  - `relevant_context_ids`
  - `selection_reasoning`
  - `needs_refinement`

当前规则实现：

- 问候类 -> `CHAT`
- 极短或显著歧义问句 -> `AMBIGUOUS`
- 包含“对比/分别/并且”等 -> `MULTI_PART`
- 其他 -> `DOC_QA`

### Stage2（细粒度）

- 输入：query + Stage1Result
- 输出：`Stage2Result`
  - `sub_problems`
  - `routing_plan`
  - `clarification_needed`
  - `overall_confidence`

当前策略：

- `needs_refinement = true` 时，进入 clarification。
- 否则切分子问题并生成 capability 计划：retrieve -> (reason) -> response。

---

## 7. 前端澄清闭环（已接通）

### API 适配

- 文件：`frontend/src/lib/api.ts`
- `askQuestion()` 已切换到 `POST /api/qa/v1/query`
- 新增 `answerClarification()` 对接 `POST /api/qa/v1/clarify/{thread_id}`
- 支持 `clarification_pending` 响应映射

### 会话 Hook

- 文件：`frontend/src/hooks/useQASession.ts`
- 新增 `clarificationThreadBySession` 状态并持久化
- `sendMessage()` 自动判断：
  - 无 pending thread -> 发 query
  - 有 pending thread -> 发 clarify
- 澄清完成后自动清理 pending thread

### QAPanel

- 文件：`frontend/src/components/QAPanel.tsx`
- 已支持 panel 内澄清续答链路（pending 时下一条输入走 clarify）

---

## 8. 测试与验证

新增测试：

- `agent/tests/test_qa_v1_context_kernel.py`
- `agent/tests/test_qa_v1_subagent_registry.py`
- `agent/tests/test_qa_v1_clarification.py`

已验证结果：

- `pytest`：`7 passed`
- 前端构建：`npm run build` 通过
- `py_compile`：新增/修改核心 Python 文件通过

---

## 9. 当前限制与后续迭代建议

当前 V1 已可运行，但仍有提升空间：

1. Stage1/Stage2 目前仍是规则主导，可逐步替换为更强的模型化决策。
2. context ranking 当前为轻量打分，可升级为 FTS + embedding 混合召回。
3. clarification 目前是一问一答恢复，可升级多轮澄清线程与超时策略。
4. subagent 目前内置默认实现，后续可按 capability 热插拔业务代理。
5. 前端会话历史加载逻辑可继续完善（当前 `switchSession` 仍留有服务端加载扩展点）。

---

## 10. 结论

QA 已从 V0 的“路由驱动问答”升级到 V1 的“Context-First 底座架构”：

- 会话隔离：已满足
- 固定格式：已满足
- 标签/摘要索引：已满足（结构化字段 + 索引表）
- 两阶段识别可落地前提：已满足
- subagent 可替换：已满足（capability registry）

下一步可以直接在这套底座上推进你后续的 subagent 改造与两阶段策略增强。
