# P1-05: LangGraph Gap Engine 图定义

## 依赖
- P0-01（Pydantic Schema）
- P1-04（PaperRetriever）

## 目的
定义 Gap Engine 的 LangGraph 有向图结构，包括 GapEngineState、8 个节点占位、Edge 路由和 SqliteSaver checkpoint，为后续节点实现提供框架。

## 执行方法
1. 在 `src/maelstrom/graph/gap_engine.py` 中定义：
   - `GapEngineState(TypedDict)` — 完整状态 schema（topic, llm_config, session_id, expanded_queries, raw_papers, papers, coverage_matrix, gap_hypotheses, critic_results, ranked_gaps, topic_candidates, search_result, current_step, error）
   - 8 个节点函数签名（初始为 pass-through 占位）：
     - topic_intake, query_expansion, paper_retrieval, normalize_dedup
     - coverage_matrix, gap_hypothesis, gap_critic, ranking_packaging
   - Edge 路由函数 `should_continue_after_retrieval`：有结果 → normalize_dedup，全部失败 → error_end
2. 在 `src/maelstrom/graph/builder.py` 中构建图：
   - `StateGraph(GapEngineState)` 添加 8 个节点
   - 添加边：START → topic_intake → query_expansion → paper_retrieval → (路由) → normalize_dedup → coverage_matrix → gap_hypothesis → gap_critic → ranking_packaging → END
   - 配置 `AsyncSqliteSaver` checkpoint
   - `compile()` 生成可执行图
3. 在 `src/maelstrom/graph/__init__.py` 导出 `build_gap_engine_graph()`

## 验收条件
- GapEngineState 包含所有必要字段
- 图可成功 compile，无循环依赖
- 8 个节点按正确顺序连接
- Edge 路由在 error 时跳转到 error_end
- SqliteSaver checkpoint 正确配置
- 占位节点可执行（pass-through 不报错）

## Unit Test
- `test_state_schema`: 验证 GapEngineState 包含所有必要字段
- `test_graph_compiles`: 验证图 compile 成功
- `test_graph_node_count`: 验证图包含 8 个节点
- `test_graph_edge_order`: 验证节点连接顺序正确
- `test_route_with_papers`: state 有 raw_papers 时路由到 normalize_dedup
- `test_route_no_papers`: state 无 raw_papers 时路由到 error_end
- `test_route_with_error`: state 有 error 时路由到 error_end
- `test_checkpoint_configured`: 验证 SqliteSaver 正确绑定
- `test_passthrough_execution`: 用占位节点执行完整图，验证不报错
