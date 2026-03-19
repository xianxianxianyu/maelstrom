# Agent, Memory, Skills, and MCP Layer

## 1. Module Definition

这一层是平台原语层，不是业务引擎层。  
系统中的横向 engines 都通过这些原语实现其内部能力。

---

## 2. Design Principle

- **Agent**：处理高不确定性的推理与判断
- **Memory**：提供状态与知识 substrate
- **Skills**：沉淀可复用的 procedure bundles
- **MCP**：标准化接入外部 tools/resources/prompts

它们不是彼此替代关系，而是互补关系。

---

## 3. Agent Runtime

### Recommended Roles
- `RetrieverAgent`
- `CriticAgent`
- `PlannerAgent`
- `WriterAgent`
- `InterpreterAgent`

### Rules
1. 不无限增殖角色
2. 角色必须有明确输入输出 schema
3. 委派必须通过 handoff manager 或明确的 node contract
4. agent 间不直接共享全量消息历史，优先共享 artifacts / summaries

### Agent Contract
```json
{
  "agent_name": "CriticAgent",
  "allowed_skills": ["gap_scoring_skill", "unsupported_claim_checker"],
  "allowed_tools": ["paper_search_profile", "evidence_lookup"],
  "inputs": ["Claim[]", "Evidence[]"],
  "outputs": ["CritiqueMemo"]
}
```

---

## 4. Memory Substrate

### Memory Types
| Memory | Scope | Example |
|---|---|---|
| Working Memory | 单次 subgraph 运行 | current node state |
| Session Memory | 单个会话 | current artifacts & approvals |
| Project Memory | 一个课题的长期知识 | past hypotheses / accepted gaps |
| Run Memory | 实验执行记录 | failed configs, metric history |
| Evidence Graph | 结构化证据关系 | claim-evidence-plan-run graph |
| Preference/Policy Memory | 用户偏好与策略 | dataset preferences, approval policy |

### Memory View Concept
不同 engine 读取同一底层 store 的不同视图：
- `GapView`
- `ReviewView`
- `PlanningView`
- `ExperimentView`

---

## 5. Skills Registry

### What is a skill here?
一个 skill 应该是：
- 可复用
- 可版本化
- 输入输出清晰
- 可被 agent 或 workflow 调用
- 尽可能 bundle instructions + scripts + schema + tests

### Suggested Skills
- `coverage_analysis_skill`
- `gap_scoring_skill`
- `claim_extraction_skill`
- `citation_alignment_skill`
- `baseline_matrix_skill`
- `ablation_planner_skill`
- `result_inference_skill`
- `unsupported_claim_checker`

### Skill Package Structure
```text
skills/
  gap_scoring/
    SKILL.md
    schema.json
    examples.md
    run.py
    tests/
```

---

## 6. MCP Gateway

### Purpose
统一接入外部资源、工具与 prompt servers。

### Recommended MCP Profiles
- `paper_search_profile`
- `web_search_profile`
- `dataset_profile`
- `git_repo_profile`
- `file_system_profile`
- `experiment_tracker_profile`

### Typical Use
- resources：文件、论文、数据库 schema
- tools：搜索、执行、查询、同步
- prompts：可复用任务模板

### Rule
内部状态（尤其 session state、evidence graph）不要完全外包给 MCP；MCP 是 integration boundary，不是你的唯一 memory source。

---

## 7. Prompt Templates

### 7.1 Agent Role Template
```text
Role: CriticAgent
Mission: 检查候选结论或候选 gap 是否存在证据不足、假设漂移、结论跳跃。
Allowed inputs: Claim[], Evidence[], RunRecord[]
Allowed outputs: CritiqueMemo
Do not:
- invent evidence
- write final report
- mutate persistent state directly
```

### 7.2 Skill Invocation Prompt
```text
请不要自行从头完成该任务。
优先检查是否存在合适 skill。
若有，请只输出：
{
  "use_skill": true,
  "skill_name": "...",
  "reason": "...",
  "expected_output_schema": "..."
}
```

---

## 8. Communication with Other Modules

### With Orchestration Runtime
- 接收 selected skills / tools / memory view
- 返回 typed artifacts 或 critique memos

### With Data Layer
- 读写 artifact refs
- 查询 evidence graph
- 写 trace sub-events

---

## 9. Reuse-First Recommendations

| Capability | Reuse Candidate | How to use |
|---|---|---|
| Agent runtime + handoffs + tracing | OpenAI Agents SDK | 若主模型在 OpenAI stack 上很合适 |
| Skill bundle conventions | OpenAI Skills concept | 借鉴 `SKILL.md`、bundle、versioning |
| Team-style experimentation | AutoGen | 用于多 agent 对照实验 |
| Tool/resource protocol | MCP | 统一外部能力接入 |
| Flow-level memory API ideas | CrewAI Memory | 可参考 unified memory API 设计 |

---

## 10. Implementation Cautions

1. 不要把所有流程都包装成 skills。
2. 不要把 MCP 当唯一集成或唯一状态层。
3. 不要让 agent 自由写底层 store；必须经 artifact / event API。
4. memory retrieval 必须按 view 与 phase 受限，避免长上下文污染。
