# P1-09: gap_hypothesis + gap_critic 节点

## 依赖
- P1-05（Gap Engine 图定义）

## 目的
实现 Gap 假设生成和评审节点。gap_hypothesis 使用 LLM 分析覆盖矩阵空白区域生成 Gap 假设，gap_critic 使用 LLM 对每个 Gap 进行评审（keep/revise/drop）。

## 执行方法
1. 在 `src/maelstrom/graph/nodes/gap_hypothesis.py` 中实现：
   - 输入：state.coverage_matrix + state.papers
   - 使用 LLM 分析覆盖矩阵中的空白区域
   - Prompt：给定覆盖矩阵和论文摘要，识别研究空白，生成结构化 GapItem
   - 每个 GapItem 包含：title, summary, gap_type, evidence_refs, confidence
   - 生成 5-15 个 Gap 假设
   - 写入 state.gap_hypotheses
2. 在 `src/maelstrom/graph/nodes/gap_critic.py` 中实现：
   - 输入：state.gap_hypotheses + state.papers
   - 对每个 GapItem 使用 LLM 评审：
     - verdict: "keep" | "revise" | "drop"
     - reasons: 评审理由列表
   - Prompt：给定 Gap 假设和相关论文，评估其新颖性、可行性、影响力
   - 写入 state.critic_results（[{gap_id, verdict, reasons}]）
3. LLM 调用使用结构化输出（JSON mode 或 function calling）确保格式一致

## 验收条件
- gap_hypothesis 生成 5-15 个结构化 GapItem
- 每个 GapItem 的 evidence_refs 引用真实的 paper_id
- gap_type 为有效枚举值（dataset/evaluation/method/deployment_setting 等）
- gap_critic 对每个 Gap 给出 verdict 和 reasons
- verdict 为 keep/revise/drop 之一
- LLM 输出格式一致，无解析错误

## Unit Test
- `test_hypothesis_count`: mock LLM，验证生成 5-15 个 GapItem
- `test_hypothesis_structure`: 验证 GapItem 字段完整（title, summary, gap_type, evidence_refs）
- `test_hypothesis_evidence_refs`: 验证 evidence_refs 引用存在的 paper_id
- `test_hypothesis_gap_type`: 验证 gap_type 为有效枚举值
- `test_critic_verdict`: mock LLM，验证每个 Gap 有 verdict
- `test_critic_verdict_values`: 验证 verdict 为 keep/revise/drop 之一
- `test_critic_reasons`: 验证每个评审包含 reasons 列表
- `test_critic_all_gaps_reviewed`: 验证所有 gap_hypotheses 都被评审
- `test_hypothesis_llm_error`: LLM 失败时设置 error 而非崩溃
