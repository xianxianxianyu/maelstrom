# P3-11: Synthesis → EvidenceMemory 回写 + Phase 联动

## 依赖
- P3-08（report_assembly — ReviewReport 持久化）
- P2-02（EvidenceMemory）
- P2-07（Session Phase Tracking — ResearchPhase）

## 目的
Synthesis Engine 完成后，将结果回写到 EvidenceMemory（供后续 Phase 和 Gap Followup 查询），并更新 Session Phase 从 ideation → grounding。同时实现 Gap → Synthesis 的数据联动。

## 执行方法

### 1. Synthesis 结果回写 EvidenceMemory

在 `report_assembly` 节点末尾或 `synthesis_service._execute_run` 完成后：

```python
mem = get_evidence_memory()

# 写入 ReviewReport 摘要
await mem.ingest_text(
    session_id, "review", report.report_id,
    f"Review: {report.topic}",
    report.executive_summary or "",
)

# 写入每个 Claim
for claim in report.claims:
    await mem.ingest_text(
        session_id, "claim", claim.claim_id,
        f"Claim: {claim.text[:80]}",
        f"{claim.text}\nType: {claim.claim_type}\nFields: {json.dumps(claim.extracted_fields)}",
    )

# 写入 FeasibilityMemo
if memo:
    await mem.ingest_text(
        session_id, "feasibility", memo.memo_id,
        f"Feasibility: {memo.verdict.value}",
        f"{memo.reasoning}\nVerdict: {memo.verdict.value}\nConfidence: {memo.confidence}",
    )
```

### 2. Phase 联动

```python
# synthesis_service._execute_run 完成后
from maelstrom.services.phase_tracker import _set_phase
await _set_phase(db, session_id, ResearchPhase.grounding)
```

### 3. Gap → Synthesis 数据传递

当用户从 Gap 结果选择一个 GapItem 进入 Synthesis 时：
- `POST /api/synthesis/run` 接收 `gap_id` 参数
- `targeted_retrieval` 节点读取该 gap 的 evidence_refs（关联论文 ID）
- 从 EvidenceMemory 中检索这些论文作为初始集合
- gap 的 title + summary 作为 targeted query 的输入

### 4. SessionContext 扩展

在 `SessionContext` 中新增 `has_synthesis_runs: bool`，供意图分类器使用：
```python
class SessionContext(BaseModel):
    ...
    has_synthesis_runs: bool = False
```

`_build_session_context` 中查询 synthesis_runs 表。

## 验收条件
- Synthesis 完成后 EvidenceMemory 中有 review / claim / feasibility 记录
- Session phase 更新为 grounding
- Gap → Synthesis 时正确读取 gap 关联论文
- SessionContext 包含 has_synthesis_runs
- EvidenceMemory 中的 claim 可被后续 search 检索到

## Unit Test
- `test_review_ingested`: synthesis 完成 → EvidenceMemory 有 review 记录
- `test_claims_ingested`: synthesis 完成 → EvidenceMemory 有 claim 记录
- `test_feasibility_ingested`: synthesis 完成 → EvidenceMemory 有 feasibility 记录
- `test_phase_updated_to_grounding`: synthesis 完成 → session phase = grounding
- `test_gap_papers_passed`: gap_id 传入 → targeted_retrieval 读取 gap 关联论文
- `test_session_context_has_synthesis`: 有 synthesis run → has_synthesis_runs = true
- `test_claims_searchable`: ingest 后的 claim 可通过 FTS 搜索到
