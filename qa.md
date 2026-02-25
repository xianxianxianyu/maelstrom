# Maelstrom QA v2 架构与落地总方案（融合版）

> 本文档用于统一说明 QA v2 的目标、架构设计、实施路线与本轮执行总结。
> 这是对历史 `qa.md` 内容的融合重写：保留核心思想，删除过重治理细节，强调“先跑通、可验证、可迭代”。

---

## 1. 文档目标

本方案回答三件事：

1. **我们要做成什么**（目标与边界）
2. **我们准备怎么做**（架构、模块、接口、路线）
3. **我们已经做到什么**（plan 与 task 执行总结）

---

## 2. 目标与边界

### 2.1 目标

- 把 QA 从“单一问答调用”升级为“可编排的多代理流水线”。
- 保持证据优先：答案必须可回溯到引用片段（citation）。
- 保持成本可控：支持超时和上下文预算硬限制。
- 保持兼容：旧接口 `/api/agent/qa` 不受影响，新能力走 `/api/agent/qa/v2`。
- 保持可迭代：先落地最小可用，再逐步增强多跳推理与观测能力。

### 2.2 非目标（当前阶段不做）

- 不引入重型基础设施（如分布式调度器、复杂事件总线改造）。
- 不在首版引入完整安全治理体系（注入策略、深度审计、数据合规生命周期等）。
- 不重写现有 Translation 等其他业务流程。

---

## 3. 架构设计（融合保留版）

## 3.1 总体架构

```text
Client(QAPanel)
  -> POST /api/agent/qa/v2
    -> PromptAgentV2 (输入规范化 + 路由决策)
    -> PlanAgentV2   (生成结构化计划)
    -> DAGExecutor   (按依赖执行节点)
        -> Retrieve / Reason / Write / Verify
    -> Verifier 不通过 => 统一回退到单跳检索 QA
  <- Response(answer, citations, confidence, route, traceId, contextBlocks)
```

## 3.2 核心设计思想

- **Prompt 与 Router/Gate 融合**：入口统一处理 query 规范化、路由选择、上下文块组织。
- **Plan 与执行解耦**：先产出结构化 plan，再由 DAG 执行，便于扩展节点与重试策略。
- **写作与校验分离**：Writing 负责组织答案，Verifier 负责“是否可信且有证据”。
- **失败统一兜底**：任何关键阶段失败，统一降级为单跳检索路径，避免请求中断。
- **观测内建**：每次请求产生 trace，累计 metrics，支持后续调优。

## 3.3 路由策略

- `FAST_PATH`：短问/轻问，快速响应。
- `DOC_GROUNDED`：文档内问答主路径，检索证据后写作。
- `MULTI_HOP`：复杂问题路径，支持多检索节点 + 推理节点。

---

## 4. 最小非模型机制（保留项）

为降低首版复杂度，仅保留 3 项必须机制：

1. **真值对齐**：grounded 路径必须有 citation，且 citation 能在证据集中命中。
2. **成本上限**：通过 `timeout_sec` 与 `max_context_chars` 做执行与上下文硬约束。
3. **失败兜底**：计划、执行或验证失败时，统一回退到单跳检索 QA。

其余治理类议题（安全策略、深度审计、数据生命周期）后置到后续产品化阶段。

---

## 5. 模块设计（按职责）

## 5.1 PromptAgentV2

职责：

- 输入标准化（query 规整）
- 路由决策（`FAST_PATH`/`DOC_GROUNDED`/`MULTI_HOP`）
- 输出 `context_blocks`

产出：`route`, `context_blocks`, `confidence`, `normalized_query`

## 5.2 PlanAgentV2

职责：根据 route 生成可执行计划（`QAPlan`）。

- `FAST_PATH`: `write -> verify`
- `DOC_GROUNDED`: `retrieve -> write -> verify`
- `MULTI_HOP`: `retrieve_primary + retrieve_secondary -> reason -> write -> verify`

## 5.3 DAGExecutor

职责：

- 按依赖执行节点
- 注入依赖节点结果到下游节点参数
- 节点失败可被上层识别并触发统一回退

## 5.4 WritingAgentV2

职责：基于 `EvidencePack` 生成回答。

- 无证据：返回保守答复
- 有证据：抽取前 3 条证据形成答案与 citation

## 5.5 VerifierAgentV2

职责：规则校验输出。

- grounded 路径缺 citation -> 不通过
- citation 不在证据中 -> 不通过
- answer 为空 -> 不通过

## 5.6 会话记忆与指标

- `QASessionMemory`：按 `session_id` 管理多轮上下文，支持 `doc_id` 过滤。
- `QAMetrics`：统计总请求、fallback、verify 失败、平均时延、route 分布。

---

## 6. API 设计（v2）

## 6.1 请求模型

`POST /api/agent/qa/v2`

```json
{
  "query": "string",
  "docId": "string | null",
  "sessionId": "string | null",
  "options": {
    "timeout_sec": 8,
    "max_context_chars": 6000
  }
}
```

## 6.2 响应模型

```json
{
  "answer": "string",
  "citations": [{ "chunkId": "string", "text": "string", "score": 0.0 }],
  "confidence": 0.0,
  "route": "FAST_PATH | DOC_GROUNDED | MULTI_HOP",
  "traceId": "string",
  "contextBlocks": []
}
```

## 6.3 观测端点

- `GET /api/agent/qa/v2/health`
- `GET /api/agent/qa/v2/trace/{trace_id}`
- `GET /api/agent/qa/v2/metrics`

---

## 7. 兼容策略

- 旧接口 `/api/agent/qa` 保持原有行为。
- 新接口 `/api/agent/qa/v2` 并行提供新能力。
- `backend/app/main.py` 同时注册 `agent_route.router` 与 `qa_v2_route.router`。

---

## 8. 落地路线（重写后的执行版）

## 8.1 Phase A：基线打通

- 新增 v2 路由与契约
- 路由注册、健康检查、trace 初始能力

验收：v1 不回归、v2 可调用、返回结构稳定。

## 8.2 Phase B：核心子代理

- Prompt/Plan/DAG/Writing/Verifier 主链路接通
- grounded 失败统一兜底

验收：主链路可执行，失败可预期降级。

## 8.3 Phase C：记忆与观测

- session memory 接入
- metrics 聚合与查询端点

验收：多轮上下文可读，metrics 可观测。

## 8.4 Phase D：稳态迭代

- 优化真实 multi-hop 策略
- 增加更系统的评测与回归
- 再逐步纳入后置治理项

---

## 9. 本轮 Plan 总结（融合你要求的内容）

本轮 plan 采用“Wave 分阶段执行”：

- **Wave 1**：基础设施与 API 骨架
- **Wave 2**：核心子代理实现
- **Wave 3**：记忆与降级机制
- **Wave 4**：质量观测最小闭环
- **Wave 5**：验证与文档同步

计划原则：

- 先保证可跑通，再逐步增强
- 每一波都有可验证产物
- 不引入超出当前目标的重治理复杂度

---

## 10. 本轮 Task 执行总结（已落地）

## 10.1 已完成项

### A. 核心架构与模块

- `agent/agents/plan_agent_v2.py`：结构化计划生成
- `agent/agents/writing_agent_v2.py`：证据约束写作
- `agent/agents/verifier_agent_v2.py`：规则校验
- `agent/core/types.py`：补齐核心类型与 `TraceContext`

### B. 路由与流程

- `backend/app/api/routes/qa_v2.py`：
  - 主接口 `POST /api/agent/qa/v2`
  - `health/trace/metrics` 端点
  - 主链路执行 + 统一回退
  - `timeout_sec`、`max_context_chars` 约束

### C. 记忆与观测

- `agent/core/qa_memory.py`：内存会话管理
- `agent/core/qa_metrics.py`：请求/失败/时延/路由统计

### D. 应用集成

- `backend/app/main.py`：注册 `qa_v2_route.router`
- 保持 v1 与 v2 并行

## 10.2 验证结果（本轮）

- 编译检查通过：新增/修改的 Python 文件 `py_compile` 通过。
- 回归测试通过：`agent/agents/test_qa_agent.py` 通过（33 passed）。
- 运行时验证通过：
  - v2 返回有效 `route`、`traceId`
  - `metrics` 可读（`total_requests`、`total_fallback`、`route_counter`）

---

## 11. 当前差距与下一步任务

当前已具备“可运行的最小闭环”，但仍有明确增量空间：

1. `MULTI_HOP` 仍是轻量版（双检索 + 合并），需升级为更真实的多跳推理策略。
2. `trace` 当前为进程内存存储，后续可接持久化。
3. 需要补充针对 `qa_v2` 的专门测试集（路由判定、verify 失败回退、预算/超时边界）。
4. 后置治理项（安全策略、深度审计、数据生命周期）按产品化阶段逐步引入。

---

## 12. 结论

本版方案已完成你要求的融合：

- **架构设计**：统一成一条从入口到验证再到回退的闭环。
- **目标想法**：明确“先跑通、可验证、可控成本、兼容旧接口”的核心方向。
- **plan + task 总结**：把本轮分波计划与实际执行结果落到文档里。

最终状态：QA v2 已从设计稿进入“可运行版本”，下一步进入“质量增强与策略深化”。
