# Research Workflow Agent Architecture Docs

本目录包含一套面向科研生命周期（选题 → 综述 → 实验设计 → 实验执行与结论推导）的双轴架构设计文档。

## Document Index

| File | Purpose |
|---|---|
| `01_system_overview.md` | 系统总览、目标、需求、2D 分层架构图、模块边界与全局通信 |
| `02_workspace_governance.md` | 交互层与治理层设计：Workspace、HITL、审批、报告查看与策略控制 |
| `03_gap_engine.md` | Gap Engine：选题发现、缺口分析、候选课题排序 |
| `04_synthesis_engine.md` | Synthesis Engine：文献综述、结论对齐、可行性论证 |
| `05_planning_engine.md` | Planning Engine：实验设计、baseline/method/metric/ablation 规划 |
| `06_experiment_engine.md` | Experiment Engine：实验记录、结果推导、证据链与复盘 |
| `07_orchestration_runtime.md` | 编排与运行时：Phase Router、DAG 模板、重试、预算、并行与中断 |
| `08_agent_memory_skills_mcp.md` | Agent/Memory/Skills/MCP 统一原语层与接口设计 |
| `09_data_observability_eval.md` | 数据底座、Artifact/Evidence、Trace、Eval、Versioning |
| `10_open_source_comparison.md` | 开源项目横向对比与选型建议 |
| `12_frontend_backend_uiux_api_report.md` | 从 start 视角整理前后端显示方式、通知接口、数据契约与耦合边界 |
| `13_assistant_ui_adoption_boundary_and_lobehub_reference.md` | 说明 assistant-ui 应复用哪些层、哪些层必须自建，以及 lobehub 仅适合作为参考的边界 |

## Recommended Reading Order

1. `01_system_overview.md`
2. `10_open_source_comparison.md`
3. `07_orchestration_runtime.md`
4. `08_agent_memory_skills_mcp.md`
5. `03` → `06` 四个业务引擎文档
6. `09_data_observability_eval.md`
7. `02_workspace_governance.md`

## Suggested Implementation Baseline

- Workflow / DAG / State: **LangGraph**
- Tool/Resource protocol: **MCP**
- Core LLM agent runtime / tracing (optional, if tightly on OpenAI stack): **OpenAI Agents SDK**
- Team-style multi-agent experiments / literature-review baseline examples: **AutoGen**
- Optional business-flow abstraction for lighter orchestration: **CrewAI Flows**
- Avoid using SOP-heavy frameworks (e.g. MetaGPT) as the primary runtime for this project.

See `10_open_source_comparison.md` for full rationale.
