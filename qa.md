# QA 子代理系统架构方案（本地化版本）

本文档将当前 Maelstrom QA 从“单一 QAAgent + 检索工具”升级为“可编排子代理系统”，并重点细化 **PromptAgent（融合 Router/Gate）** 的成熟设计。

---

## 1. 目标与边界

### 1.1 目标

- 让 QA 具备可规划、可追踪、可扩展的多代理执行能力。
- 保证答案“证据优先”，支持结构化引用与可追溯性。
- 降低无效 token 消耗，提升缓存命中与响应稳定性。
- 与现有代码兼容，采用增量演进而非推倒重来。

### 1.2 非目标（Phase 1 不做）

- 不引入重型基础设施（Kafka/ES/分布式调度器）。
- 不重写现有 Translation 流程。
- 不移除现有 `/api/agent/qa`，保留兼容路径。

---

## 2. 总体架构（PromptAgent 融合 Router/Gate）

```text
Client(QAPanel)
  -> /api/agent/qa/v2
    -> QAWorkflowOrchestrator
      -> PromptAgent (Context Curation + Router/Gate)
      -> PlanAgent   (Plan + DAG tasks)
      -> DAGExecutor (parallel/dep/retry/cancel)
          -> TaskAgents (Retrieve / Rewrite / EvidenceMerge / ConflictResolve ...)
      -> WritingAgent (grounded answer)
      -> VerifierAgent (citation-faithfulness checks)
    -> Response(answer, citations, confidence, trace)
```

### 2.1 模块职责

- **PromptAgent（含 Router/Gate）**：统一输入、上下文治理、路径选择（FastPath / DocPath / MultiHop）。
- **PlanAgent**：将问题与可用资源转为结构化执行计划（DAG）。
- **DAGExecutor**：按依赖执行任务图，收集证据包。
- **TaskAgents**：原子节点，单职责输出结构化结果。
- **WritingAgent**：基于证据包生成最终回答。
- **VerifierAgent**：校验回答与引用一致性，防止“带引用幻觉”。

### 2.2 与现有项目映射

- 入口沿用：`backend/app/api/routes/agent.py`
- 基础抽象沿用：`agent/base.py`、`agent/registry.py`
- 任务与取消沿用：`backend/app/services/task_manager.py`、`CancellationToken`
- 事件流沿用：`agent/event_bus.py`（前端可订阅阶段事件）
- 旧实现兼容：`agent/agents/qa_agent.py` 作为 fallback

---

## 3. 关键改进（相对原方案）

在“Prompt -> Plan -> DAG -> Writer”主干上，建议增加以下关键能力：

1. **VerifierAgent（必加）**：答案出站前做证据一致性检查。
2. **结构化计划输出（必加）**：PlanAgent 输出必须是 schema 校验通过的 JSON，不允许自由文本计划。
3. **预算护栏（必加）**：限制 DAG 深度/并行度/节点数/重试次数。
4. **降级路径（必加）**：计划失败时回退到单跳检索 QA，而不是直接报错。
5. **上下文持久化（必加）**：会话与摘要落盘，避免重启丢失。

### 3.1 成熟度缺口清单（非代码层）

#### P0（上线前必须补齐）

- 质量定义：明确“答对/有证据/可解释”的判定标准。
- 路由阈值表：复杂度、歧义度、证据充分度、预算压力的阈值与回退规则。
- 证据契约：citation 字段规范与最小可审计要求。
- 失败处理规范：检索空、冲突证据、计划失败、验证失败的统一策略。
- 记忆生命周期：保留、压缩、遗忘、用户纠错回写机制。

#### P1（可持续迭代必须补齐）

- 评测体系：离线基准集 + 线上行为指标。
- SLO/SLA：按路由定义 P50/P95 时延与成功率目标。
- 成本治理：token/模型预算、超预算降级路径、成本告警阈值。
- 版本治理：Prompt/Router/Plan 策略版本化与灰度回滚方案。
- 观测审计：trace 回放、事件字典、失败归因链路。

#### P2（产品化成熟项）

- 安全策略：prompt injection、越权提问、敏感信息泄露防护。
- 跨文档边界：doc 缺失时如何选文档，跨文档冲突如何表达不确定性。
- 反馈闭环：差评样本进入评测集和策略更新机制。

### 3.2 大模型与系统边界总原则

- 大模型负责语义理解与表达：意图识别、query rewrite、摘要与写作。
- 系统负责约束与真值：权限、安全、引用映射、预算、路由闸门。
- 任何影响正确性和可追溯性的关键决策，不可只依赖一次 LLM 判定。

---

## 4. PromptAgent 成熟方案（Router/Gate 融合）

PromptAgent 不仅“拼 prompt”，而是 QA 流程的“控制塔入口”：

- 规范化输入
- 选择执行路径
- 裁剪上下文
- 生成统一 PromptBundle
- 更新会话记忆

### 4.1 输入契约（建议）

```json
{
  "question": "string",
  "session_id": "string",
  "doc_id": "string|null",
  "user_profile": {
    "language": "zh",
    "style": "academic_concise"
  },
  "runtime": {
    "latency_budget_ms": 12000,
    "max_tokens": 6000
  }
}
```

### 4.2 输出契约（PromptBundle）

```json
{
  "normalized_query": "string",
  "intent": "fact|explain|compare|summarize|multi_hop|unknown",
  "route": "FAST_PATH|DOC_GROUNDED|MULTI_HOP|CLARIFY|BLOCK",
  "doc_scope": ["doc_123"],
  "constraints": {
    "must_cite": true,
    "no_hallucination": true,
    "max_dag_depth": 3,
    "max_parallel": 4,
    "max_nodes": 8
  },
  "context_blocks": [
    {"type": "session_summary", "content": "...", "priority": 1},
    {"type": "recent_turns", "content": "...", "priority": 2},
    {"type": "doc_profile", "content": "...", "priority": 3}
  ],
  "cache_key": "sha256:...",
  "trace": {
    "turn_id": "t_xxx",
    "prompt_agent_version": "v1"
  }
}
```

---

## 5. Router/Gate 规则（融合在 PromptAgent）

### 5.1 路由类型

- `FAST_PATH`：简单问题，低成本路径（可直达 WritingAgent 或单跳检索）。
- `DOC_GROUNDED`：文档内问题，必须检索并附引用。
- `MULTI_HOP`：需要分解子问题、并行检索、冲突消解。
- `CLARIFY`：关键信息缺失，先澄清。
- `BLOCK`：违反策略（敏感/越权/无证据硬答）。

> 关键点：Router/Gate 的最终输出不只是“路由类型”，还要给出 **执行模式（Execution Mode）**。

执行模式建议：

- `R0_DIRECT_WRITE`：直接进入 WritingAgent（仅会话/结构化记忆可回答）。
- `R1_ONE_SHOT_RETRIEVE`：单次检索 -> WritingAgent -> VerifierAgent。
- `R2_MULTI_RETRIEVE`：多次检索（查询改写或多源）-> EvidenceMerge -> Writing/Verifier。
- `R3_DAG_PLAN`：进入 PlanAgent + DAGExecutor（复杂问题）。
- `R4_CLARIFY`：返回澄清问题。
- `R5_BLOCK`：拒答或安全模板答复。

### 5.2 判定维度

- 问题复杂度：是否包含多实体、多约束、多步骤。
- 作用域明确性：是否提供 `doc_id` 或可从 session 推断。
- 证据要求强度：是否要求“出处/比较/证明”。
- 时延预算：低预算优先 FastPath。
- 风险等级：高风险问题强制走 DocGrounded + Verifier。

补充判定信号（建议落地为评分）：

- `retrieval_sufficiency`：预检索是否已拿到高质量证据（命中数、top score、覆盖度）。
- `context_stability`：会话历史是否稳定且无冲突结论。
- `ambiguity_score`：是否存在“这个/它/该方法”等未指代清晰用语。
- `cost_pressure`：当前预算是否允许多跳计划。

### 5.3 示例规则（可编码）

- 若 `doc_id` 存在且问题涉及“文中/这篇/该论文” -> `DOC_GROUNDED`。
- 若包含“比较/权衡/原因链路/多条件筛选” -> `MULTI_HOP`。
- 若问题短且实体单一且历史无冲突 -> `FAST_PATH`。
- 若缺少核心指代目标（如“这个方法”但无上下文） -> `CLARIFY`。
- 若请求违背策略或证据不足仍要求确定结论 -> `BLOCK` 或保守答复。

### 5.4 路由到哪里（执行矩阵）

| 条件 | 路由类型 | 执行模式 | 执行链路 |
|---|---|---|---|
| 会话记忆已包含稳定答案，且无需新证据 | FAST_PATH | R0_DIRECT_WRITE | PromptAgent -> WritingAgent -> VerifierAgent |
| 简单文档问答，预检索证据充分 | DOC_GROUNDED | R1_ONE_SHOT_RETRIEVE | PromptAgent -> Retriever(1次) -> Writing -> Verifier |
| 简单但证据不足，需改写重搜 | DOC_GROUNDED | R2_MULTI_RETRIEVE | PromptAgent -> QueryRewrite + Retriever(2-3次) -> EvidenceMerge -> Writing -> Verifier |
| 多跳复杂问题/跨段推理/冲突证据 | MULTI_HOP | R3_DAG_PLAN | PromptAgent -> PlanAgent -> DAGExecutor(TaskAgents...) -> Writing -> Verifier |
| 缺少关键指代或范围 | CLARIFY | R4_CLARIFY | PromptAgent -> ClarifyTemplate |
| 安全策略触发/强制无证据结论 | BLOCK | R5_BLOCK | PromptAgent -> SafeResponse |

### 5.5 索引到哪里（核心回答）

建议采用“三层索引 + 一层术语索引”，全部可先落在现有 SQLite 体系（`data/papers.db`）中，避免引入重型 infra。

1. **I0 会话记忆索引（Session Memory Index）**
   - 用途：支持 `R0_DIRECT_WRITE` 与低成本上下文注入。
   - 数据：turn/segment、tags、summary、最近引用。
   - 建议表：`qa_turns`, `qa_segments`。

2. **I1 文档分块索引（Document Chunk Index）**
   - 用途：回答文档事实问题的主证据源。
   - 数据来源：`Translation/<translation_id>/translated.md`（可选补充 `ocr_raw.md`）。
   - 粒度：chunk（建议 300-800 tokens），保留 `doc_id`, `translation_id`, `chunk_id`, `source`, `section`, `offset`。
   - 检索：FTS +（可选）向量分数。
   - 建议表：`qa_doc_chunks`, `qa_doc_chunks_fts`。

3. **I2 文档元数据索引（Corpus Metadata Index）**
   - 用途：当 `doc_id` 缺失时，先缩小候选文档集合。
   - 复用：现有 `papers` + `papers_fts`（`agent/tools/paper_repository.py`）。

4. **I3 术语索引（Glossary Index）**
   - 用途：术语一致性、消歧与写作规范。
   - 数据来源：`Translation/glossaries/*.json` + 术语服务。

> 标识统一建议：`doc_id` 以 `task_id` 为主键，`translation_id` 作为版本/快照 ID。这样可与现有 `PaperRepository` 一致。

### 5.6 一次或多次检索/索引的触发策略

#### A. 一次检索（R1）

- 条件：问题简单、范围明确、预检索 top-k 证据分数高。
- 过程：检索一次即可写作，Verifier 只做一致性检查。

#### B. 多次检索（R2）

- 条件：一次检索不足（命中少、分数低、证据冲突）。
- 过程：
  1) QueryRewrite 生成 1-2 个改写问法
  2) 每个问法检索
  3) EvidenceMerge 去重与冲突标注
  4) 再交给 Writing/Verifier

#### C. 多跳计划（R3）

- 条件：多子问题、跨章节依赖、对比/因果链要求。
- 过程：PlanAgent 输出 DAG，节点并行执行（受预算约束）。

#### D. 索引构建触发（不是每次都全量重建）

- 翻译完成后触发增量索引（推荐主路径）。
- 若 QA 首次命中文档但发现未建索引，触发懒加载索引。
- 文档内容变更时，仅对受影响 chunk 重建。

### 5.7 Router/Gate 伪代码（建议）

```python
def route(prompt_input):
    if policy_violation(prompt_input):
        return BLOCK, R5_BLOCK

    scope = resolve_scope(prompt_input.doc_id, prompt_input.session_id)
    if scope.ambiguous:
        return CLARIFY, R4_CLARIFY

    pre = preflight_retrieve(scope, prompt_input.question)
    simple = complexity_score(prompt_input.question) < 0.35

    if simple and context_can_answer_from_memory(prompt_input.session_id):
        return FAST_PATH, R0_DIRECT_WRITE

    if simple and pre.sufficient:
        return DOC_GROUNDED, R1_ONE_SHOT_RETRIEVE

    if simple and not pre.sufficient:
        return DOC_GROUNDED, R2_MULTI_RETRIEVE

    return MULTI_HOP, R3_DAG_PLAN
```

### 5.8 哪些环节可由大模型直接判定，哪些必须走非模型机制

| 环节 | 可由 LLM 直接判定 | 必须由系统机制判定 |
|---|---|---|
| 问题理解 | intent 分类、歧义识别、改写建议 | 最终 route 生效与否（阈值、预算、安全） |
| 路由决策 | 给出 route 候选和置信度 | 依据规则表做最终路由与降级 |
| 检索策略 | query rewrite、召回关键词生成 | 实际索引查询、top-k 切分、doc_scope 约束 |
| 证据组织 | 证据摘要、冲突解释草案 | citation 结构映射（chunk/page/source）、证据存在性校验 |
| 答案生成 | 语言组织、结构化表达 | 事实约束、无证据硬答拦截、敏感内容策略 |
| 会话记忆 | tag/summary 提取 | 持久化、TTL、压缩与删除、冲突覆盖策略 |
| 运营治理 | 误差模式解释 | SLO、成本、告警、版本开关、灰度与回滚 |

### 5.9 Router/Gate 的混合决策流水线（推荐）

1. **LLM 评分**：给出 `complexity`, `ambiguity`, `retrieval_need`, `risk` 四个分数。
2. **规则校正**：系统按阈值表强制修正（安全/预算/doc_scope/策略优先）。
3. **预检索验证**：做一次低成本 preflight，计算 `retrieval_sufficiency`。
4. **最终执行模式**：输出 `R0-R5` 之一，并写入 trace。
5. **失败回退**：若执行中失败，按固定矩阵回退（`R3 -> R2 -> R1 -> R4`）。

> 约束：`R0_DIRECT_WRITE` 只允许在低风险且无需新增证据时触发；涉及事实断言/比较结论/用户要求出处时，至少走 `R1`。


---

## 6. PromptAgent 上下文管理（缓存友好）

这是该方案的重点：每次/每段对话都做标准化保存，支持高命中缓存与低噪音上下文。

### 6.1 标准化存储模型

#### Turn 级（每轮）

```json
{
  "turn_id": "turn_20260225_001",
  "session_id": "sess_abc",
  "ts": 1760000000,
  "doc_scope": ["doc_123"],
  "user_query_raw": "...",
  "user_query_norm": "...",
  "assistant_answer": "...",
  "route": "DOC_GROUNDED",
  "tags": ["qa", "methodology", "comparison"],
  "summary_short": "一句话摘要",
  "summary_medium": "3-5句摘要",
  "citations": ["c_001", "c_003"],
  "quality": {"grounded": true, "confidence": 0.81}
}
```

#### Segment 级（段落/片段）

```json
{
  "segment_id": "seg_turn_001_02",
  "turn_id": "turn_20260225_001",
  "role": "assistant",
  "text": "...",
  "tags": ["claim", "evidence", "limitation"],
  "summary": "该段核心信息...",
  "embedding_ref": "emb_xxx",
  "token_count": 132
}
```

### 6.2 上下文分层（推荐）

- **L0 Recent Raw**：最近 N 轮原文（高保真，短窗口）。
- **L1 Turn Summaries**：每轮摘要（中窗口）。
- **L2 Session Rolling Summary**：会话滚动总结（长窗口）。
- **L3 Topic/Doc Memory**：按标签/文档聚合的长期记忆。

构建 Prompt 时优先顺序：`L2 -> L0 -> L1 -> L3`（按预算动态裁剪）。

### 6.3 缓存友好策略

1. **规范化序列化**：字段固定顺序，空值策略统一。
2. **稳定排序**：context blocks 按 `(priority, ts, id)` 排序。
3. **去噪规则**：移除寒暄、重复确认、低信息密度片段。
4. **模板分层**：系统前缀、策略约束、动态上下文分开构建，提升前缀缓存命中。
5. **哈希键构造**：
   - `cache_key = hash(model + route + normalized_query + context_block_ids + policy_version)`
6. **增量更新**：只重算受影响块，不全量重建上下文。

### 6.4 Tag 与 Summary 策略

- 每轮至少产出：`intent_tag + topic_tag + action_tag`。
- 每段可选产出：`claim/evidence/quote/risk/decision`。
- 摘要双层：
  - `summary_short`：检索路由用（1句）
  - `summary_medium`：Prompt 注入用（3-5句）
- 当 session 超阈值（如 20 轮）触发 compaction：
  - 保留最近 6 轮 raw
  - 历史收敛为 rolling summary + topic memory

---

## 7. PlanAgent 与 DAG 任务规范

### 7.1 Plan 输出结构（必须可校验）

```json
{
  "plan_id": "plan_xxx",
  "route": "MULTI_HOP",
  "nodes": [
    {"id": "n1", "type": "rewrite_query", "deps": []},
    {"id": "n2", "type": "retrieve", "deps": ["n1"]},
    {"id": "n3", "type": "evidence_merge", "deps": ["n2"]},
    {"id": "n4", "type": "draft_answer", "deps": ["n3"]},
    {"id": "n5", "type": "verify", "deps": ["n4"]}
  ],
  "budget": {"max_nodes": 8, "max_depth": 3, "timeout_ms": 12000}
}
```

### 7.2 DAG Executor 规则

- 只执行 schema 合法节点。
- 节点超时可重试 1 次，仍失败则走降级分支。
- 支持取消（沿用 `CancellationToken`）。
- 阶段事件写入 EventBus，便于前端进度可视化。

---

## 8. WritingAgent 与 VerifierAgent 规则

### 8.1 WritingAgent

- 输入仅为 `EvidencePack + AnswerPolicy`。
- 输出必须包含：`answer`, `citations[]`, `confidence`, `limitations`。
- 严禁无证据扩写；证据不足时必须明确“不足以判断”。

### 8.2 VerifierAgent（新增）

- 检查每条关键结论是否有 citation 映射。
- 检查 citation 是否存在、是否与结论语义一致。
- 若失败：
  - 轻度失败 -> 重写局部段落
  - 重度失败 -> 回退到保守回答模板

---

## 9. API 与前端建议

### 9.1 API 演进

- 保留：`POST /api/agent/qa`（兼容旧版）
- 新增：`POST /api/agent/qa/v2`

`/qa/v2` 返回建议：

```json
{
  "answer": "...",
  "citations": [
    {
      "citation_id": "c_001",
      "doc_id": "doc_123",
      "source": "translated.md",
      "chunk_id": "chunk_22",
      "snippet": "...",
      "score": 0.87
    }
  ],
  "confidence": 0.81,
  "grounded": true,
  "route": "DOC_GROUNDED",
  "trace_id": "qa_run_xxx"
}
```

### 9.2 前端改造最小步

- `translate/page.tsx`：将 `translationId` 传入 `QAPanel docId`。
- `QAPanel.tsx`：展示 route、confidence、citation 明细；后续接入 DAG 进度事件。

---

## 10. 落地路线（建议）

### Phase 0（快速增益）

- 接通 `docId` 作用域。
- PromptAgent 最小版（规范化 + Router/Gate + context block 输出）。
- 修复 `context` 字段“有定义未使用”的问题。

### Phase 1（子代理化）

- 上线 PlanAgent + DAGExecutor + WritingAgent + VerifierAgent。
- 保留旧 QAAgent 作为降级路径。

### Phase 2（记忆与缓存）

- 会话/段落标准化存储（turn+segment+tags+summary）。
- rolling summary + topic memory + cache key 策略。

### Phase 3（质量闭环）

- 指标与回放：grounded rate、citation coverage、latency、fallback ratio。
- 反馈学习：用户点踩样本进入评测集。

---

## 11. PromptAgent 验收标准（建议）

1. 路由准确率：`FAST/DOC/MULTI_HOP` 分类 F1 >= 0.85（离线集）。
2. 缓存命中：相似问法二次请求命中率 >= 40%（阶段性目标）。
3. 上下文质量：注入 prompt 的无效内容比例下降 >= 30%。
4. 时延稳定：P95 时延不劣于现有系统 + 25%。
5. 可追踪性：每次回答均可追溯 `trace_id + route + context_blocks`。

### 11.1 仍需非模型机制解决的开放问题（保留项）

以下问题不能靠“再问一次大模型”自动解决，必须通过制度/规则/工程机制闭环：

- **真值对齐**：引用与答案的一致性需要结构化验证器，不是提示词可替代。
- **成本上限**：预算控制和超时熔断必须由执行器硬约束。
- **安全边界**：越权、注入、敏感问答的拦截需要策略引擎。
- **可靠回退**：计划失败时的可预测降级路径必须确定化。
- **可审计性**：线上事故复盘需要 trace、事件日志、版本记录。
- **数据治理**：会话数据保留/删除/脱敏/纠错无法仅靠模型保证。

---

## 12. 结论

你提出的 `PromptAgent -> PlanAgent -> DAG -> WritingAgent` 是正确方向。要把它做成“成熟系统”，关键在于：

- PromptAgent 必须承担 Router/Gate 与上下文治理，成为真正入口控制层。
- Plan 必须结构化、可执行、可失败回退。
- Writer 必须证据约束，Verifier 必须把关。
- 记忆必须标准化、分层化、缓存友好。

按本方案落地，可以在不重写现有工程的前提下，把 QA 从“功能可用”升级到“可运维、可扩展、可审计”。


---

## 13. 大模型无法独立解决的问题（必须由系统机制兜底）

以下问题不能仅依赖大模型自我判断解决，必须通过确定性规则、工程机制或制度流程闭环：

### 13.1 真值与证据对齐

- **citation 物理存在性**：大模型无法验证引用的 chunk_id 是否真实存在于存储中，必须查询索引确认。
- **引用与结论一致性**：模型可能"理解"证据但生成与证据矛盾的结论，需要结构化验证器检查映射关系。
- **证据时效性**：模型无法自动判断引用的内容是否已被新版本覆盖或失效。

**必须机制**：物理索引查询、结构化 citation 校验、版本一致性检查。

### 13.2 成本与资源硬边界

- **token 预算熔断**：模型不会自动停止生成或选择更便宜的模型，需要执行器硬中断。
- **超时控制**：模型调用无法自我超时或降级，需要外部计时器强制终止。
- **并发与速率限制**：模型无法自我调度以避免系统过载，需要令牌桶或队列机制。

**必须机制**：硬超时计时器、预算计数器、降级策略（超预算时切换模型或返回缓存）。

### 13.3 安全与权限边界

- **prompt injection 防御**：模型容易被恶意指令覆盖系统提示，需要输入 sanitization 和注入检测。
- **越权访问控制**：模型不会自动判断"用户是否有权查看某文档"，需要权限检查。
- **有害内容生成**：模型可能生成危险建议，需要输出过滤和安全策略拦截。
- **数据泄露防护**：模型不会自动识别是否正在泄露敏感信息，需要数据分类和脱敏机制。

**必须机制**：输入 sanitization、RBAC 权限检查、输出安全过滤、敏感数据识别与脱敏。

### 13.4 可靠回退与失败处理

- **级联失败恢复**：当一个子代理失败时，模型不会自动知道如何"降级"到更简单路径。
- **死循环检测**：模型不会自我检测到"一直在重复相似查询"。
- **确定性回退**：需要明确的规则来决定"R3失败时回退到R2，R2失败时回退到R1"。
- **超时降级**：当某个节点超时时，模型不会自动选择返回部分结果或缓存内容。

**必须机制**：失败类型分类、降级矩阵、重试计数器、兜底策略、部分结果返回逻辑。

### 13.5 可审计性与可追溯性

- **完整链路记录**：大模型调用本身不会自动记录"为什么选了这个路由、用了哪些证据"。
- **版本一致性**：模型输出无法自我证明"使用的是哪个版本的 prompt"。
- **事后归因**：出现问题时，需要外部 trace 来复盘是哪个环节出错，模型无法自我诊断。
- **合规审计**：对于敏感领域，需要完整的决策日志供人工审计，模型不会自动生成。

**必须机制**：trace_id 全链路传递、事件日志、版本标签、快照记录、审计日志格式。

### 13.6 数据治理与生命周期

- **数据保留策略**：大模型不会自动"遗忘"过期会话或执行数据脱敏。
- **用户权利实现**：用户要求"删除我的历史"时，需要系统级操作，模型层无法实现。
- **数据一致性**：分布式或长周期运行中，模型无法自我保证"读取的是最新版本的数据"。
- **隐私合规**：GDPR/个保法要求的"被遗忘权"、"可携带权"等，需要工程机制支持。

**必须机制**：TTL 管理、软删除/硬删除策略、数据脱敏规则、一致性校验、合规工作流。

---

## 14. 大模型与系统边界总原则

| 维度 | 大模型负责（语义层） | 系统负责（约束层） |
|---|---|---|
| **理解** | 意图识别、歧义检测、改写生成 | 权限校验、安全过滤 |
| **推理** | 证据摘要、冲突解释草案 | citation 真实性校验、逻辑一致性验证 |
| **生成** | 语言组织、结构化表达 | 预算控制、超时熔断、降级策略 |
| **记忆** | tag/summary 内容提取 | 持久化、TTL、版本管理、隐私合规 |
| **路由** | 复杂度/歧义度评分建议 | 阈值判定、强制执行、失败回退 |
| **治理** | 模式解释、建议生成 | SLO 监控、成本告警、审计追溯 |

**核心原则**：凡是影响**正确性、安全性、成本可控性、可审计性**的决策，必须有多重非模型机制兜底，不能仅依赖 LLM 的"自我判断"。

---

## 15. 仍需非模型机制解决的开放问题（保留项）

以下问题不能靠"再问一次大模型"自动解决，必须通过制度/规则/工程机制闭环：

1. **真值对齐**：引用与答案的一致性需要结构化验证器，不是提示词可替代。
2. **成本上限**：预算控制和超时熔断必须由执行器硬约束。
3. **安全边界**：越权、注入、敏感问答的拦截需要策略引擎。
4. **可靠回退**：计划失败时的可预测降级路径必须确定化。
5. **可审计性**：线上事故复盘需要 trace、事件日志、版本记录。
6. **数据治理**：会话数据保留/删除/脱敏/纠错无法仅靠模型保证。

---

**按本方案落地，可以在不重写现有工程的前提下，把 QA 从"功能可用"升级到"可运维、可扩展、可审计"。**
