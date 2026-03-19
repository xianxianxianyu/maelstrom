# CHORE-002: 未实现能力与后续任务拆分

## 依赖
- 01_system_overview
- P3-10
- P3-11
- CHORE-001

## 目的
基于 `docs/start/` 的完整蓝图和当前 `docs/V0/` 已承诺范围，梳理系统中仍未实现或仅部分实现的能力，并按当前落地优先级拆分为 P0 / P1 / P2 任务。

## 执行方法
1. 先区分两类缺口：
   - 第一类：已经在当前 V0 / P2 / P3 文档中承诺，但代码还未完整交付的能力。
   - 第二类：属于 `docs/start/` 的完整平台蓝图，但当前仓库还没有开始或只做了雏形的能力。
2. 再按优先级拆分任务：
   - `P0`：优先补齐当前版本承诺范围内的缺口，避免“文档已写、产品未到位”。
   - `P1`：推进下一层核心研究工作流能力，使系统从 Gap + QA + Synthesis 走向完整闭环。
   - `P2`：补平台化、治理、可观测性和扩展性基础设施。
3. 每个任务都尽量固定到模块，便于后续拆 issue 或继续生成实现文档。

## 执行方法

### P0：补齐当前版本已承诺但尚未完整交付的能力

#### T0.1 Artifact API 补齐 ✅
- [x] 新增 `GET /api/artifacts/{artifact_id}`
- [x] 新增 `GET /api/artifacts?session_id=...&type=...`
- [x] 支持按 `session_id`、`type` 查询 Gap / TopicCandidate / ReviewReport / Feasibility 等 artifact
- [x] 前端至少提供一个基础读取入口，便于后续 Report Viewer 和 Workspace 复用

涉及模块：
- `src/maelstrom/api/`
- `src/maelstrom/db/artifact_repo.py`
- `src/maelstrom/schemas/`

说明：
- `requirements_and_feasibility.md` 已将 Artifact API 写进 V0 设计，但当前代码里没有独立 artifact router。

#### T0.2 Gap Engine 真正的节点级恢复与持久化 ✅
- [x] 用真正的 LangGraph checkpointer 或等价持久化机制替换当前主要依赖内存 `_run_state` 的恢复模式
- [x] 把 `current_step`、关键中间结果和恢复所需最小状态持久化到 SQLite
- [x] 页面恢复时可以重建已完成步骤，而不是只从”恢复后收到的新 SSE 事件”开始显示
- [x] 明确 completed / running / failed 三类恢复语义

涉及模块：
- `src/maelstrom/services/gap_service.py`
- `src/maelstrom/graph/builder.py`
- `src/maelstrom/db/gap_run_repo.py`
- `frontend/src/hooks/useGapStream.ts`
- `frontend/src/app/gap/page.tsx`

说明：
- 当前已经能恢复“最近 run”，但仍不是文档里定义的 checkpoint 级恢复。

#### T0.3 Gap → Synthesis 前端联动补齐 ✅
- [x] 在 Gap 结果卡片上新增 “进入 Synthesis / 深入综述” 入口
- [x] 跳转到 `/synthesis?gap_id=...&session_id=...`
- [x] `SynthesisInput` 改为”从当前 session 的 gap 列表选择”，而不是手填 `gap_id`
- [x] Synthesis 页面支持自动读取 URL 中的 `gap_id` 并预填或自动启动

涉及模块：
- `frontend/src/components/gap/`
- `frontend/src/app/gap/page.tsx`
- `frontend/src/components/synthesis/SynthesisInput.tsx`
- `frontend/src/app/synthesis/page.tsx`

说明：
- P3-10 已经承诺了这个链路，但当前仍是简化输入版。

#### T0.4 Synthesis 历史运行恢复 ✅
- [x] 为 Synthesis 增加按 `session_id` 查询最近 run 的恢复逻辑
- [x] 页面刷新或切出切回后，支持恢复最近一次 synthesis 结果或运行状态
- [x] 与 Gap Engine 保持一致的 session-first / run restore 体验

涉及模块：
- `src/maelstrom/api/synthesis.py`
- `src/maelstrom/db/synthesis_run_repo.py`
- `src/maelstrom/services/synthesis_service.py`
- `frontend/src/hooks/useSynthesisStream.ts`
- `frontend/src/app/synthesis/page.tsx`

说明：
- 当前 Synthesis 能运行，但还不像 Gap 一样具备完整恢复闭环。

#### T0.5 文档与实现一致性清理 ✅
- [x] 清理当前仍存在的界面乱码（确认不存在）
- [x] 修正文档中已经过时的描述，避免和当前路由/API 实现冲突
- [x] 将 `CHORE-001` 中已修与未修状态同步到最新事实

涉及模块：
- `frontend/src/`
- `src/maelstrom/services/`
- `docs/`

说明：
- 这是低风险高收益任务，能降低后续排查成本。

### P1：补齐完整研究工作流主干能力

#### T1.1 Planning Engine 落地 ✅
- [x] 定义 `ExperimentPlan`、`BaselineMatrix`、`AblationPlan`、`ExecutionChecklist` 的 schema
- [x] 新增 Planning graph / service / API / frontend 页面
- [x] 输入来自 Synthesis 的 `ReviewReport`、`FeasibilityMemo`、`Hypothesis`
- [x] 输出结构化实验规划，支持后续 Experiment Engine 消费

涉及模块：
- `src/maelstrom/schemas/`
- `src/maelstrom/graph/`
- `src/maelstrom/services/`
- `src/maelstrom/api/`
- `frontend/src/app/`
- `frontend/src/components/`

说明：
- 这是从 “能找题 + 做综述” 走向 “能设计实验” 的关键一跳。

#### T1.2 Experiment Engine 落地 ✅
- [x] 定义 `RunRecord`、`Conclusion`、`ReflectionNote` 等 schema
- [x] 提供实验记录录入、结果导入、失败原因记录、图表附件关联能力
- [x] 生成结论候选与复盘摘要
- [x] 和 Session / EvidenceMemory 形成闭环

涉及模块：
- `src/maelstrom/schemas/`
- `src/maelstrom/services/`
- `src/maelstrom/api/`
- `frontend/src/app/`
- `frontend/src/components/`

说明：
- 这是 `start/` 里 Phase D 的核心能力，目前仓库中还没有对应实现。

#### T1.3 Workspace 视角整合
- [ ] 增加统一的 workspace / project 入口，而不只是分散的 `/chat`、`/gap`、`/synthesis`
- [ ] 将 session 视为研究工作区，集中展示最近 Gap、Synthesis、文档、对话和后续计划
- [ ] 提供跨引擎的上下文导航，而不是依赖侧边栏分散跳转

涉及模块：
- `frontend/src/app/`
- `frontend/src/components/layout/`
- `src/maelstrom/api/sessions.py`

说明：
- 这是从“功能页集合”向“研究工作台”演进的关键任务。

#### T1.4 Report Viewer 独立化 ✅
- [x] 将 Gap 结果、Synthesis 报告、后续 Planning / Experiment 结果统一成可独立访问的报告视图
- [x] 支持按 artifact 或 run_id 查看结果，不依赖原始页面状态
- [x] 为后续分享、审阅、追踪和审计做准备

涉及模块：
- `frontend/src/app/`
- `frontend/src/components/`
- `src/maelstrom/api/`
- `src/maelstrom/db/artifact_repo.py`

#### T1.5 Session 内研究阶段流转补齐 ✅
- [x] 明确 session 在 `ideation / grounding / planning / execution` 之间的切换条件
- [x] 前端展示当前 research phase
- [x] 在 Gap、Synthesis、Planning、Experiment 完成后自动更新阶段

涉及模块：
- `src/maelstrom/services/phase_tracker.py`
- `src/maelstrom/services/phase_router.py`
- `src/maelstrom/api/sessions.py`
- `frontend/src/app/`

说明：
- 当前 phase 基础设施已有一部分，但还没有形成完整阶段工作流。

### P2：平台化、治理、可观测性与扩展能力

#### T2.1 Evidence Graph 真正落地
- [ ] 从当前 `evidence_memory` 文本检索扩展到结构化 claim-evidence-gap-plan-run-conclusion 图关系
- [ ] 定义关系边模型和查询接口
- [ ] 支持从 report、claim、gap、experiment run 反查上下游证据链

涉及模块：
- `src/maelstrom/schemas/`
- `src/maelstrom/db/`
- `src/maelstrom/services/evidence_memory.py`
- `src/maelstrom/api/`

说明：
- 当前只有 EvidenceMemory FTS，不是 `start/` 所描述的 Evidence Graph。

#### T2.2 Trace / Event Bus / Audit 基础设施
- [ ] 统一记录各引擎运行事件、节点开始结束、外部调用、错误和人工介入点
- [ ] 将 SSE 事件和内部运行事件区分处理
- [ ] 为回放、排障、评测、审计提供统一 event schema

涉及模块：
- `src/maelstrom/services/`
- `src/maelstrom/db/`
- `src/maelstrom/api/`

说明：
- 当前有 SSE，但没有平台级 trace/event bus。

#### T2.3 Eval Harness 与回归评测
- [ ] 设计 Gap / Synthesis / Planning / Experiment 的质量评测集
- [ ] 固化自动化评测输出格式
- [ ] 区分功能测试、质量评测、离线回放三类验证

涉及模块：
- `tests/`
- `src/maelstrom/services/`
- `docs/`

#### T2.4 MCP Gateway 与 Skills Registry
- [ ] 设计统一 tool/resource/provider 接入层
- [ ] 将现有外部能力接入从业务 service 中抽离
- [ ] 为未来引入更多 agent-native 能力保留统一协议入口

涉及模块：
- `src/maelstrom/services/`
- `src/maelstrom/api/`
- 新增 `mcp/` 或等价模块

说明：
- 这部分在 `start/` 中是平台原语，但当前仓库还没有真正开始。

#### T2.5 Governance / HITL / Policy Console
- [ ] 为关键节点增加人工确认点
- [ ] 提供简单审批记录与拒绝/重试机制
- [ ] 增加策略级开关，例如允许哪些外部检索、哪些自动运行、哪些写回 Evidence

涉及模块：
- `frontend/src/app/`
- `src/maelstrom/services/`
- `src/maelstrom/api/`

#### T2.6 多用户与权限体系
- [ ] 设计用户、组织、工作区、会话归属模型
- [ ] 增加认证、授权和会话隔离
- [ ] 将当前单机单用户 session 模型扩展为可协作模型

涉及模块：
- `src/maelstrom/api/`
- `src/maelstrom/db/`
- `frontend/src/app/`

说明：
- 这项不属于当前单机版本必须项，但如果往平台方向走，迟早要补。

## 验收条件
- 文档明确区分“当前版本承诺未补齐”与“完整蓝图后续能力”。
- 文档按 P0 / P1 / P2 给出可执行任务，而不是仅给概念分类。
- 每个任务都至少指出一组涉及模块，便于后续继续生成实现文档或 issue。
- 文档可直接作为下一阶段排期输入使用。
