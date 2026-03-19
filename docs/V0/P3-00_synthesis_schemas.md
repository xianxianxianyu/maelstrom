# P3-00: Synthesis Engine Artifact Schemas

## 依赖
- P0-01（Pydantic Schema 基础）
- P1-09（GapItem schema）

## 目的
定义 Synthesis Engine 的全部 Artifact Schema：Claim、Evidence、ReviewReport、FeasibilityMemo、SynthesisRunState。这些是 Synthesis Engine 7 个节点之间传递的核心数据结构。

## 执行方法

### 1. Claim Schema — `src/maelstrom/schemas/claim.py`

```python
class ClaimType(str, Enum):
    method_effectiveness = "method_effectiveness"
    dataset_finding = "dataset_finding"
    metric_comparison = "metric_comparison"
    limitation = "limitation"
    assumption = "assumption"
    negative_result = "negative_result"

class Claim(BaseModel):
    claim_id: str
    paper_id: str                     # 来源论文 ID
    claim_type: ClaimType
    text: str                         # claim 原文
    evidence_refs: list[str] = []     # 关联的 Evidence ID
    confidence: float = Field(ge=0, le=1)
    extracted_fields: dict = {}       # problem/method/dataset/metric/result/limitation
```

### 2. Evidence Schema — `src/maelstrom/schemas/evidence.py`

```python
class Evidence(BaseModel):
    evidence_id: str
    source_id: str                    # 来源论文 ID
    source_span: str = ""             # "page 4, paragraph 2" 或 "abstract"
    snippet: str                      # 原文片段
    modality: Literal["text", "table", "figure"] = "text"
    retrieved_via: str = ""           # 检索来源标记
    created_at: datetime
```

### 3. ReviewReport Schema — `src/maelstrom/schemas/review_report.py`

```python
class ConsensusPoint(BaseModel):
    statement: str
    supporting_claim_ids: list[str]
    strength: Literal["strong", "moderate", "weak"] = "moderate"

class ConflictPoint(BaseModel):
    statement: str
    claim_ids: list[str]             # 冲突的 claim 对
    conflict_source: str = ""         # "dataset_difference" / "metric_difference" / ...
    requires_followup: bool = False

class ReviewReport(BaseModel):
    report_id: str
    session_id: str
    source_gap_id: str | None = None  # 来源 GapItem ID（如有）
    topic: str
    claims: list[Claim] = []
    evidences: list[Evidence] = []
    consensus_points: list[ConsensusPoint] = []
    conflict_points: list[ConflictPoint] = []
    open_questions: list[str] = []
    paper_count: int = 0
    created_at: datetime
```

### 4. FeasibilityMemo Schema — `src/maelstrom/schemas/feasibility.py`

```python
class FeasibilityVerdict(str, Enum):
    advance = "advance"       # 值得立项，进入 Planning
    revise = "revise"         # 需要调整方向
    reject = "reject"         # 不建议继续

class FeasibilityMemo(BaseModel):
    memo_id: str
    report_id: str            # 关联的 ReviewReport
    verdict: FeasibilityVerdict
    gap_validity: str         # 缺口是否真实成立
    existing_progress: str    # 现有工作是否已接近解决
    resource_assessment: str  # 实验资源要求是否合理
    reasoning: str            # 综合理由
    confidence: float = Field(ge=0, le=1)
    created_at: datetime
```

### 5. SynthesisRunState — `src/maelstrom/schemas/synthesis.py`

```python
class SynthesisRunState(BaseModel):
    run_id: str
    session_id: str
    source_gap_id: str | None = None
    topic: str
    status: RunStatus = RunStatus.pending
    # Pipeline state
    targeted_papers: list[PaperRecord] = []
    filtered_papers: list[PaperRecord] = []
    claims: list[Claim] = []
    evidences: list[Evidence] = []
    consensus_points: list[ConsensusPoint] = []
    conflict_points: list[ConflictPoint] = []
    review_report: ReviewReport | None = None
    feasibility_memo: FeasibilityMemo | None = None
    # Metadata
    current_step: str = "pending"
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
```

## 验收条件
- 所有 Schema 可正常实例化和序列化
- ClaimType 包含 6 种类型
- FeasibilityVerdict 包含 3 种判定
- SynthesisRunState 包含 7 个节点的中间状态字段
- 所有 Schema 在 `schemas/__init__.py` 中导出

## Unit Test
- `test_claim_schema`: Claim 字段完整，ClaimType 6 种
- `test_evidence_schema`: Evidence 字段完整
- `test_review_report_schema`: ReviewReport 包含 consensus/conflict/open_questions
- `test_feasibility_memo_schema`: FeasibilityMemo 包含 verdict + 4 维评估
- `test_synthesis_run_state`: SynthesisRunState 包含全部中间状态字段
- `test_feasibility_verdict_enum`: 3 种 verdict 值
- `test_serialization_roundtrip`: 各 Schema JSON 序列化/反序列化一致
