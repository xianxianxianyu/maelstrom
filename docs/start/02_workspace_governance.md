# Workspace and Governance Module

## 1. Module Definition

Workspace and Governance 模块是系统的人机边界层。它负责把系统的内部 phase-driven workflow 暴露为研究人员可控、可审计、可中断的工作台，而不是一个黑箱 Agent。

---

## 2. Responsibilities

1. 提供统一任务入口：topic、question、paper set、experiment logs。
2. 展示结构化输出：Gap 报告、文献综述、计划书、结论与反思。
3. 管理审批点：课题确认、可行性确认、实验计划批准、结论发布前确认。
4. 展示 trace / lineage / evidence linkage。
5. 设置策略：预算、时延、模型、允许的工具、MCP profiles、权限。

---

## 3. Internal Submodules

| Submodule | Purpose | Input | Output |
|---|---|---|---|
| Workspace UI | 任务发起、文档浏览、表单输入 | user input | task request |
| Chat / QA Adapter | 支持自然语言交互 | user prompt | routed request |
| Report Viewer | 渲染 artifacts | report artifacts | readable views |
| Approval Console | 人工审批与修改 | approval request | decision event |
| Policy Console | 调整预算、工具、审批策略 | config input | policy config |
| Trace Viewer | 可视化运行轨迹 | trace events | timeline / node graph |

---

## 4. Communication with Other Modules

### To Orchestration Runtime
- `start_task`
- `resume_after_approval`
- `override_template`
- `adjust_budget`
- `abort_run`

### From Orchestration Runtime
- `approval_requested`
- `phase_changed`
- `run_completed`
- `run_failed`
- `trace_available`

### To Data Layer
- fetch artifacts
- fetch traces
- fetch metrics

---

## 5. Key Screens

1. **Research Home**
   - 输入 topic / goal
   - 选择目标阶段（Gap / Review / Planning / Experiment）
2. **Phase Workspace**
   - 当前 phase、当前 artifacts、正在运行的 subgraph
3. **Approval Center**
   - 待确认课题
   - 待确认可行性
   - 待批准实验计划
   - 待发布结论
4. **Trace Explorer**
   - 节点时间线
   - skill/tool 调用
   - evidence 使用情况
5. **Lineage Viewer**
   - gap → review → plan → run → conclusion 依赖链

---

## 6. Implementation Suggestions

### Recommended Reuse
- 前端无需自己造复杂 IDE，可先用普通 React/Next.js 或你已有前端栈。
- Trace 可直接对接 LangSmith / OpenTelemetry-compatible backend / OpenAI tracing dashboards（视选型而定）。
- Approval 流程可基于 runtime interrupt/checkpoint 实现，不建议在前端自己发明并发状态机。

### Backend API Suggestions
- `POST /tasks`
- `GET /sessions/{id}`
- `GET /artifacts/{id}`
- `GET /traces/{trace_id}`
- `POST /approvals/{approval_id}`
- `POST /runs/{id}/resume`
- `POST /runs/{id}/abort`

---

## 7. Prompt Engineering / UX Templates

### 7.1 Task Intake Template
```text
你是 Research Workspace Intake Router。
请将用户输入归类为以下阶段之一：
1. ideation
2. grounding
3. planning
4. execution

输出 JSON：
{
  "phase": "...",
  "goal_summary": "...",
  "expected_artifacts": ["..."],
  "needs_human_gate": true/false
}
```

### 7.2 Approval Summary Template
```text
请以审稿式方式概括本次待审批结果：
- 目标
- 主要依据
- 风险点
- 建议动作：approve / revise / reject
- 若 revise，给出最小修改建议
```

---

## 8. Non-Functional Requirements

- 审批动作必须有审计日志
- 所有 artifact 页面都必须能跳到来源 evidence / run records
- 允许用户在审批点修正 hypotheses / constraints / datasets
- 支持 phase 级回退与重跑
