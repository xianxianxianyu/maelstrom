# Open Source Comparison and Selection

## 1. Purpose

本页用于回答一个核心问题：  
**这套科研 workflow agent 应该尽量复用哪些开源框架，哪些只适合借鉴思想，哪些不适合作为主干。**

---

## 2. Candidate Projects

- LangGraph
- OpenAI Agents SDK
- CrewAI
- AutoGen / Magentic-One pattern
- MetaGPT
- OpenHands
- MCP (protocol, not a runtime framework)

---

## 3. Comparison Table

| Project | Best at | Strengths | Weaknesses for this project | Recommended Role |
|---|---|---|---|---|
| LangGraph | Stateful workflow / DAG / checkpoints | Graph-native, subgraphs, persistence, HITL, debugging-friendly | You still design prompts/roles yourself | **Primary orchestration runtime** |
| OpenAI Agents SDK | Agent runtime, handoffs, tracing, guardrails, MCP integration | Clean primitives, built-in tracing, structured handoffs | Best fit if you are on OpenAI stack; not itself a full workflow engine | **Optional agent runtime / tracing layer** |
| CrewAI | Flow-style automation + crews | Nice separation of Flows and Crews, built-in memory concepts | Can become abstraction-heavy; less graph-explicit than LangGraph | **Secondary reference / optional lighter flow layer** |
| AutoGen | Multi-agent teams and experimentation | Team patterns, literature review examples, tracing support | Group-chat style can overcomplicate deterministic workflows | **Reference for team experiments / baselines** |
| Magentic-One pattern | Open-ended orchestrator-led teams | Strong pattern for dynamic delegation, ledgers, retries | Too open-ended as the default backbone for a research workflow system | **Borrow ideas only** |
| MetaGPT | SOP-driven multi-agent roleplay | Strong SOP/productization mindset | Heavy role-play/SOP style, less suitable as core runtime for research workflow | **Borrow SOP and document ideas only** |
| OpenHands | Code-centric agent platform | Great for coding/workspace automation, composable SDK | Project is code-agent centered, not research-workflow centered | **Use only if code-heavy experiment automation becomes a major scope** |
| MCP | Tools/resources/prompts protocol | Standardized integration boundary, ecosystem momentum | Not a workflow or memory runtime by itself | **Mandatory protocol layer** |

---

## 4. Recommended Stack by Layer

| Layer | Best Choice | Why |
|---|---|---|
| Workspace UI | Custom app | Needs project-specific UX |
| Phase / DAG orchestration | LangGraph | Best fit for phase-driven subgraphs and checkpoints |
| Agent runtime | OpenAI Agents SDK or custom wrappers | Good primitives, tracing, handoffs |
| Team experimentation | AutoGen | Good for baseline experiments and literature-review patterns |
| Skills packaging | Custom, inspired by OpenAI Skills | Need project-specific schema, but reuse bundle idea |
| External tools/resources | MCP | Standardize integration |
| Data / Evidence / Trace | Custom + OpenTelemetry + DB/graph store | Needs project-specific artifact/evidence model |

---

## 5. Selection Recommendations

## Option A — Most Balanced (Recommended)
- LangGraph = orchestration backbone
- MCP = external integration boundary
- Custom artifact/evidence layer
- OpenAI Agents SDK = optional tracing/handoffs if model stack matches
- AutoGen = experimental sandbox only

**Use when:** 你要做稳、可解释、可复现的 research workflow system。

## Option B — OpenAI-leaning Stack
- LangGraph or minimal custom runtime
- OpenAI Agents SDK as core agent runtime
- OpenAI-style skills bundles
- MCP for tools/resources
- custom evidence/data layer

**Use when:** 你高度绑定 OpenAI stack，想要 tracing/handoffs/guardrails 快速落地。

## Option C — Flow-Heavy Business Stack
- CrewAI Flows + selected crews
- MCP
- custom artifact/evidence layer

**Use when:** 你更偏业务流程自动化而不是强图结构和强 checkpoint 语义。

---

## 6. Detailed Rationale

### Why LangGraph first?
因为你的系统本质是：
- phase-driven
- DAG/subgraph-heavy
- checkpoint-sensitive
- human-review-sensitive
- artifact/state-centric

LangGraph 对 shared state、subgraphs、persistence、threads/checkpoints 的抽象和你的需求最贴合。

### Why not pure AutoGen / Magentic-One?
因为你的主链路不是开放式、无限探索的多 agent 协作，而是“稳定流程 + 少数高不确定节点”。  
如果一开始就把主干做成 group chat / speaker selection，系统会更难控、更难评测。

### Why not pure MetaGPT?
你的系统不是模拟一个软件公司 SOP，而是一个研究生命周期 runtime。  
MetaGPT 更适合借鉴“中间文档产物”和 SOP 思路，而不是直接作为底座。

### Why MCP is mandatory
如果不统一协议，paper search、repo access、dataset browsing、file system、experiment trackers 都会变成各写各的工具适配层。MCP 可以把这些接入规范化。

---

## 7. Reuse Checklist

| Capability | Build | Reuse | Choice |
|---|---|---|---|
| DAG runtime | ❌ | ✅ | LangGraph |
| Handoff / guardrails / tracing | ❌ | ✅ | OpenAI Agents SDK or OpenTelemetry |
| Memory substrate | ✅ | partial | Need custom because research artifacts/evidence are domain-specific |
| Skills packaging | ✅ | partial | Reuse OpenAI-style bundle idea |
| External protocol | ❌ | ✅ | MCP |
| Literature-review baseline agents | ❌ | ✅ | AutoGen example patterns |
| SOP docs and structured role ideas | ❌ | ✅ | MetaGPT ideas only |

---

## 8. Final Recommendation

**Final stack recommendation for this project:**

1. **LangGraph** for orchestration, subgraphs, checkpoints, HITL
2. **MCP** for external tools/resources/prompts integration
3. **Custom artifact/evidence/memory layer** for research-specific state
4. **OpenAI Agents SDK (optional but strong)** for agent runtime primitives, tracing, handoffs, guardrails
5. **AutoGen as reference sandbox**, not as the production backbone
6. **MetaGPT/OpenHands only as idea donors**, not as the main runtime

---

## 9. Reference Links

- LangGraph docs
- OpenAI Agents SDK docs
- MCP specification
- CrewAI docs
- AutoGen docs
- Magentic-One docs / paper
- MetaGPT GitHub
- OpenHands GitHub
