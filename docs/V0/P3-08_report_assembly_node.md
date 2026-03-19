# P3-08: Report Assembly 节点

## 依赖
- P3-07（feasibility_review — state["feasibility_memo"]）
- P3-06（conflict_analysis — state["consensus_points"], state["conflict_points"]）
- P3-04（claim_extraction — state["claims"], state["evidences"]）
- P3-00（ReviewReport schema）

## 目的
Synthesis Engine 最后一个节点：将前 6 个节点的所有中间结果组装为最终的 ReviewReport，持久化到 DB 和 EvidenceMemory。

## 执行方法

### 1. 节点实现 — `src/maelstrom/graph/synthesis_nodes/report_assembly.py`

```python
async def report_assembly(state: dict) -> dict:
    """
    1. 汇总 claims, evidences, consensus_points, conflict_points, open_questions
    2. 调用 LLM 生成结构化摘要（可选，用于 report 的 executive summary）
    3. 组装 ReviewReport 对象
    4. 关联 FeasibilityMemo
    5. 写入 state["review_report"]
    6. 持久化到 synthesis_runs.result_json
    7. 将 ReviewReport 写入 EvidenceMemory（供后续 Phase 查询）
    """
```

### 2. Executive Summary 生成（LLM）

```text
你是研究综述撰写者。
请根据以下信息生成一段 executive summary（150-300 字）：

研究方向：{topic}
论文数量：{paper_count}
提取的 Claims 数量：{claim_count}
共识点：{consensus_summary}
冲突点：{conflict_summary}
可行性判定：{verdict}

输出一段连贯的综述摘要，涵盖主要发现、关键共识、主要冲突和可行性结论。
```

### 3. ReviewReport 组装

```python
report = ReviewReport(
    report_id=str(uuid4()),
    session_id=state["session_id"],
    source_gap_id=state.get("source_gap_id"),
    topic=state["topic"],
    claims=state["claims"],
    evidences=state["evidences"],
    consensus_points=state["consensus_points"],
    conflict_points=state["conflict_points"],
    open_questions=state.get("open_questions", []),
    paper_count=len(state.get("filtered_papers", [])),
    executive_summary=summary,
    created_at=datetime.now(timezone.utc),
)
```

### 4. 持久化
- `synthesis_runs.result_json` ← ReviewReport + FeasibilityMemo 序列化
- EvidenceMemory ← ingest_text(source_type="review", content=executive_summary)
- Claims 和 Evidences 写入 EvidenceMemory（供 Gap Followup 等查询）

### 5. SSE 事件
推送 `result` 事件，包含完整 ReviewReport + FeasibilityMemo。

## 验收条件
- ReviewReport 包含所有字段（claims, evidences, consensus, conflicts, open_questions）
- FeasibilityMemo 关联到 ReviewReport
- Executive summary 生成（LLM mock）
- 结果持久化到 synthesis_runs
- ReviewReport 写入 EvidenceMemory
- SSE `result` 事件包含完整数据
- LLM summary 失败时使用默认摘要（不阻塞）

## Unit Test
- `test_assembly_complete_report`: 所有中间结果 → 完整 ReviewReport
- `test_assembly_includes_feasibility`: report 关联 FeasibilityMemo
- `test_assembly_executive_summary`: LLM 生成 summary（mock）
- `test_assembly_summary_fallback`: LLM 失败 → 默认摘要
- `test_assembly_persisted`: result_json 写入 DB
- `test_assembly_evidence_memory`: ReviewReport 写入 EvidenceMemory
- `test_assembly_empty_claims`: 无 claims → report 仍生成（claims=[]）
