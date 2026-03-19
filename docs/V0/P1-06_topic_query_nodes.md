# P1-06: topic_intake + query_expansion 节点

## 依赖
- P1-05（Gap Engine 图定义）

## 目的
实现 Gap Engine 前两个节点：topic_intake 校验用户输入并提取关键词，query_expansion 使用 LLM 生成多个检索变体查询，提升论文检索的召回率。

## 执行方法
1. 在 `src/maelstrom/graph/nodes/topic_intake.py` 中实现：
   - 校验 topic 非空、长度合理（10-500 字符）
   - 提取关键词（简单分词或 LLM 辅助）
   - 记录 session_id 和 current_step
   - 校验失败时设置 error 字段
2. 在 `src/maelstrom/graph/nodes/query_expansion.py` 中实现：
   - 使用 LLM（通过 state.llm_config 配置）生成 3-5 个检索变体查询
   - Prompt 设计：给定 topic，生成不同角度的学术检索查询（同义词、子领域、方法论角度）
   - 将原始 topic 也加入 expanded_queries（确保至少有原始查询）
   - 更新 current_step
3. LLM 调用使用 langchain-openai / langchain-anthropic，根据 provider 动态选择

## 验收条件
- topic_intake：有效 topic 通过校验，无效 topic 设置 error
- query_expansion：生成 3-5 个不同角度的检索查询
- expanded_queries 包含原始 topic
- LLM 配置正确透传（provider/model/key/temperature）
- current_step 正确更新

## Unit Test
- `test_topic_intake_valid`: 有效 topic 通过，state 无 error
- `test_topic_intake_empty`: 空 topic 设置 error
- `test_topic_intake_too_short`: 过短 topic 设置 error
- `test_query_expansion_count`: mock LLM，验证生成 3-5 个查询
- `test_query_expansion_includes_original`: 验证 expanded_queries 包含原始 topic
- `test_query_expansion_diversity`: 验证生成的查询互不相同
- `test_query_expansion_llm_config`: 验证 LLM 调用使用正确的 provider 和 model
- `test_query_expansion_llm_error`: LLM 调用失败时回退到仅使用原始 topic
