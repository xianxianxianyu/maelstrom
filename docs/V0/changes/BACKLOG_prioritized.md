# Maelstrom 待办优先级排序

> 截至 2026-03-18，基于 CHORE-001 / CHORE-002 / FIX-004 / CHORE-003 / CHORE-004 / CHORE-005 及代码审查汇总。
> 已完成项标记 ✅，仅未完成项参与后续排期。

---

## P0 — 阻塞核心体验，需立即处理

| # | 任务 | 来源 | 状态 | 说明 |
|---|------|------|------|------|
| 1 | Synthesis 历史运行恢复 | CHORE-002 T0.4 | ✅ CHORE-004 | 三引擎 hook 添加 loadResult，页面添加 restore useEffect |
| 2 | Artifact API 补齐 | CHORE-002 T0.1 | ✅ 已实现 | `GET /api/artifacts/{id}` 和 `GET /api/artifacts?session_id=&type=` 均已注册 |
| 3 | FIX-004 验证任务收尾 | FIX-004 T1.8/T2.6/T3.5 | ✅ CHORE-004 | 验证 checklist 已全部勾选 |
| 4 | Gap→Synthesis gap_id 直传 | CHORE-002 T0.3 | ✅ CHORE-004 | SynthesisInput 添加 gap picker 下拉，从 session 的 gap 结果选择 |

## P1 — 功能完整性，近期处理

| # | 任务 | 来源 | 状态 | 说明 |
|---|------|------|------|------|
| 5 | Planning/Experiment 页面 run restore | CHORE-001 #3 | ✅ CHORE-004 | 与 Synthesis restore 一起完成 |
| 6 | `/reports` 页面实现 | 代码审查 | ✅ CHORE-005 | 新建 reports 列表页，Sidebar 添加 Reports 入口 |
| 7 | UI 乱码清理 | CHORE-001 #6 | ✅ 确认不存在 | 二次扫描确认所有文件均为合法 UTF-8，无乱码 |
| 8 | FIX-004 T3.4 路由迁移评估 | FIX-004 T3.4 | ✅ 评估完成 | 暂不迁移，当前 query param 模式已统一，迁移风险收益比不合理 |
| 9 | Session 阶段流转补齐 | CHORE-002 T1.5 | ✅ CHORE-005 | 新增 advance_phase_on_completion，四引擎完成时自动推进 phase |
| 10 | Workspace 后端端点确认 | 代码审查 | ✅ 已确认 | `GET /api/sessions/{id}/workspace` 已实现，返回 session 元数据 + 各引擎 run 列表 |
| 11 | Report Viewer 独立化 | CHORE-002 T1.4 | ✅ CHORE-005 | ArtifactRenderer 增强，复用 ReportView/PlanView/FeasibilityCard 等引擎组件渲染 |

## P2 — 质量与可维护性

| # | 任务 | 来源 | 状态 | 说明 |
|---|------|------|------|------|
| 12 | 测试套件同步 | CHORE-001 #7 | ✅ 确认通过 | 前端 32/32 通过，后端 356/356 通过（4 skip），无需修复 |
| 13 | 文档与实现一致性清理 | CHORE-002 T0.5 | ✅ CHORE-006 | CHORE-001/CHORE-002/FIX-004 三份文档已同步到当前实现状态 |
| 14 | Gap Engine 节点级 checkpoint 恢复 | CHORE-002 T0.2 | ✅ CHORE-006 | 四引擎已有 progress_json 持久化，SSE 重连时 replay 已完成步骤，启动时 orphan run 标记 failed |

## P3 — 平台化演进，按需推进

| # | 任务 | 来源 | 状态 | 说明 |
|---|------|------|------|------|
| 15 | Evidence Graph 结构化 | CHORE-002 T2.1 | ✅ CHORE-008 | SQL CTE lineage, structured graph API (typed nodes+edges), FTS search endpoint, edge CRUD, session summary, gap_service ingest_gap 补齐 |
| 16 | Trace / Event Bus / Audit | CHORE-002 T2.2 | 未开始 | 统一 event schema，区分 SSE 事件与内部运行事件，支持回放和审计 |
| 17 | Eval Harness | CHORE-002 T2.3 | 未开始 | 各引擎质量评测集，自动化评测输出格式 |
| 18 | MCP Gateway | CHORE-002 T2.4 | ✅ CHORE-007 | 7 tools (4 categories), 3 resource providers, tool detail/category filter/provider list API, JSON Schema input_schema |
| 19 | Governance / HITL / Policy Console | CHORE-002 T2.5 | 骨架 | 后端 hitl_manager + policy_service 存在，前端控制台 UI 未做 |
| 20 | 多用户与权限 | CHORE-002 T2.6 | 骨架 | auth.py / user_repo.py stub only，无真实认证授权和会话隔离 |

---

## 建议执行顺序

```
第一批（P0）✅ 全部完成
  #1 Synthesis run restore
  #2 Artifact API
  #3 FIX-004 验证收尾
  #4 gap_id 直传 + gap picker

第二批（P1）✅ 全部完成
  #5 Planning/Experiment restore
  #6 /reports 页面
  #7 UI 乱码（确认不存在）
  #8 路由迁移评估（评估完成，暂不迁移）
  #9 Session 阶段流转
  #10 Workspace 后端确认
  #11 Report Viewer 渲染增强

第三批（P2）✅ 全部完成
  #12 测试套件（确认全部通过）
  #13 文档清理
  #14 Checkpoint 恢复

按需（P3）← 下一步
  #15-#20 平台化能力
```

## 依赖关系

```
#2 Artifact API  ←  #11 Report Viewer（Report Viewer 依赖 Artifact API）✅ #2 已完成
#1 Synthesis restore  ←  #5 Planning/Experiment restore（同模式复用）✅ 均已完成
#3 FIX-004 验证  ←  无阻塞，纯验证 ✅
#4 gap_id 直传  ←  无阻塞，前端改动 ✅
#15 Evidence Graph  ←  #16 Trace/Audit（共享 event schema 设计）
```
