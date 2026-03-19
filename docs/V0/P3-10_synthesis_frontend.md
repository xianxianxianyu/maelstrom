# P3-10: Synthesis Engine 前端页面

## 依赖
- P3-09（Synthesis API — 全部端点）
- P2-05（useRouter hook）
- P1-13（Gap 前端模式参考）

## 目的
实现 Synthesis Engine 的前端页面，包括：启动入口（从 Gap 结果选择 gap 或直接输入 topic）、7 步流水线进度展示、ReviewReport 结果展示、FeasibilityMemo 展示。

## 执行方法

### 1. 页面路由 — `frontend/src/app/synthesis/page.tsx`

主页面布局：
- 顶部：Header "Synthesis Engine"
- 左侧：输入区（topic 输入 或 gap 选择器）
- 右侧：进度 + 结果展示

### 2. 输入组件 — `frontend/src/components/synthesis/SynthesisInput.tsx`

双入口模式：
- Tab 1: "从 Gap 选择" — 下拉列表展示当前 session 的 gap runs 结果中的 GapItem，选择后自动填充 topic
- Tab 2: "直接输入" — 文本输入框，输入 topic
- "开始综述" 按钮 → POST /api/synthesis/run

### 3. 进度组件 — `frontend/src/components/synthesis/SynthesisProgress.tsx`

复用 Gap Engine 的 RunProgress 模式，展示 7 个步骤：
```
1. 精准检索 (targeted_retrieval)
2. 相关性过滤 (relevance_filtering)
3. Claim 提取 (claim_extraction)
4. 引用绑定 (citation_binding)
5. 共识/冲突分析 (conflict_analysis)
6. 可行性评估 (feasibility_review)
7. 报告生成 (report_assembly)
```

每步显示状态：pending / running / done / error

### 4. SSE Hook — `frontend/src/hooks/useSynthesisStream.ts`

```typescript
function useSynthesisStream() {
  // state: steps[], claims[], conflicts[], report, feasibility, status, error
  // start(runId): EventSource → /api/synthesis/run/{runId}/stream
  // events: step_start, step_complete, claims_extracted, conflict_found, result, error, __done__
}
```

### 5. 结果组件

**ClaimList** — `frontend/src/components/synthesis/ClaimList.tsx`
- 表格展示 Claim 列表：claim_type, text, confidence, source_span
- 按 claim_type 分组或按 confidence 排序
- 点击展开 extracted_fields 详情

**ConflictCard** — `frontend/src/components/synthesis/ConflictCard.tsx`
- 卡片展示冲突点：statement, conflict_source, requires_followup 标记
- 红色标记需要后续验证的冲突

**ConsensusCard** — `frontend/src/components/synthesis/ConsensusCard.tsx`
- 卡片展示共识点：statement, strength badge (strong/moderate/weak)

**FeasibilityCard** — `frontend/src/components/synthesis/FeasibilityCard.tsx`
- 卡片展示 FeasibilityMemo：
  - verdict badge（advance=绿色, revise=黄色, reject=红色）
  - 四维评估展开
  - confidence 进度条

**ReportView** — `frontend/src/components/synthesis/ReportView.tsx`
- 综合展示 ReviewReport：
  - Executive summary
  - Claims 区域（嵌入 ClaimList）
  - Consensus 区域
  - Conflicts 区域
  - Open Questions 列表
  - Feasibility 区域（嵌入 FeasibilityCard）

### 6. Gap 页面集成

在 Gap 结果页的每个 GapCard 上新增 "深入综述" 按钮：
- 点击后跳转到 `/synthesis?gap_id={gap_id}&session_id={session_id}`
- Synthesis 页面自动读取 gap 信息并启动

## 验收条件
- /synthesis 页面可访问
- 从 Gap 选择 gap 或直接输入 topic 均可启动
- 7 步进度实时展示
- Claims 表格正确渲染
- Consensus/Conflict 卡片正确渲染
- FeasibilityCard 显示 verdict badge + 四维评估
- ReportView 综合展示所有结果
- Gap 页面 "深入综述" 按钮跳转正确

## Unit Test（vitest）
- `test_SynthesisInput_topic`: 输入 topic → 调用 start run
- `test_SynthesisInput_gap_select`: 选择 gap → 自动填充 topic
- `test_SynthesisProgress_steps`: 7 个步骤正确渲染
- `test_useSynthesisStream_events`: SSE 事件 → 状态更新
- `test_ClaimList_render`: claims 数据 → 表格渲染
- `test_ConflictCard_render`: conflict 数据 → 卡片渲染 + 红色标记
- `test_FeasibilityCard_verdict`: advance → 绿色 badge
- `test_ReportView_complete`: 完整数据 → 所有区域渲染
