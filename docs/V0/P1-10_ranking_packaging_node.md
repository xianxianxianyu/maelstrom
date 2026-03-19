# P1-10: ranking_packaging 节点

## 依赖
- P1-05（Gap Engine 图定义）

## 目的
实现最终的排序打包节点，过滤被 critic drop 的 Gap，对保留的 Gap 评分排序，生成 TopicCandidate 推荐。

## 执行方法
1. 在 `src/maelstrom/graph/nodes/ranking_packaging.py` 中实现：
   - 过滤：移除 critic verdict 为 "drop" 的 Gap
   - 对 verdict 为 "revise" 的 Gap，使用 LLM 修订（可选，V0 可简化为保留原始）
   - 评分：对每个保留的 Gap 计算 scores（novelty, feasibility, impact），使用 LLM 辅助
   - 排序：按 confidence * weighted_score 降序排列
   - 生成 TopicCandidate：从 top-N Gap 生成研究主题候选
     - title: 基于 Gap 生成的研究主题标题
     - related_gap_ids: 关联的 Gap ID
     - recommended_next_step: 建议的下一步
     - risk_summary: 风险摘要
   - 写入 state.ranked_gaps 和 state.topic_candidates

## 验收条件
- dropped Gap 不出现在 ranked_gaps 中
- ranked_gaps 按评分降序排列
- 每个 Gap 的 scores 包含 novelty/feasibility/impact（0-1 范围）
- 生成至少 1 个 TopicCandidate
- TopicCandidate 的 related_gap_ids 引用真实的 gap_id

## Unit Test
- `test_filter_dropped`: 验证 verdict="drop" 的 Gap 被过滤
- `test_keep_kept`: 验证 verdict="keep" 的 Gap 保留
- `test_scores_range`: 验证 scores 各维度在 0-1 范围
- `test_ranking_order`: 验证 ranked_gaps 按评分降序
- `test_topic_candidate_generated`: 验证至少生成 1 个 TopicCandidate
- `test_topic_candidate_refs`: 验证 related_gap_ids 引用存在的 gap_id
- `test_topic_candidate_fields`: 验证 TopicCandidate 字段完整
- `test_all_dropped`: 所有 Gap 被 drop 时，ranked_gaps 为空，topic_candidates 为空
