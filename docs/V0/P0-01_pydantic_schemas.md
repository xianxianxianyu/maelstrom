# P0-01: Pydantic Schema 定义

## 依赖
- P0-00（项目骨架）

## 目的
定义 V0 所有核心数据模型，作为前后端 API 契约和数据库序列化的基础。统一的 Schema 确保各模块间数据流转类型安全。

## 执行方法
1. 在 `src/maelstrom/schemas/` 下创建模块文件：
   - `llm_config.py` — `LLMConfig` model（provider, model_name, api_key, base_url, temperature, max_tokens, embedding_model, embedding_api_key）
   - `session.py` — `Session` model（session_id, title, status, created_at, updated_at, artifact_refs, gap_runs, chat_message_count, indexed_doc_count）
   - `paper.py` — `PaperRecord` model（paper_id, title, authors, abstract, year, venue, doi, external_ids, pdf_url, source, keywords, citation_count, retrieved_at）；`Author` model；`ExternalIds` model
   - `gap.py` — `GapItem` model（gap_id, title, summary, gap_type, evidence_refs, confidence, scores, session_id, created_at）；`GapScores` model
   - `topic.py` — `TopicCandidate` model（candidate_id, title, related_gap_ids, recommended_next_step, risk_summary, session_id, created_at）
   - `gap_analysis.py` — `GapAnalysisResult` model（run_id, session_id, topic, status, papers: list[PaperRecord], search_result, coverage_matrix: dict, ranked_gaps: list[GapItem], topic_candidates: list[TopicCandidate], created_at, completed_at）。**注意**：持久化完整 papers[] 和 coverage_matrix（非仅 summary），确保前端详情页有稳定数据源
   - `search.py` — `SourceStatus` model；`SearchResult` model
   - `common.py` — `ErrorResponse` model；共用枚举（`ProviderEnum`, `SessionStatus`, `RunStatus`）
2. 所有 model 使用 Pydantic v2 `BaseModel`，字段加类型注解和 `Field` 描述
3. 在 `schemas/__init__.py` 统一导出

## 验收条件
- 所有 model 可正常实例化，字段校验生效（如 temperature 范围 0-2）
- `LLMConfig` 的 `api_key` 在 local provider 时可为 None
- JSON 序列化/反序列化往返一致
- 所有 model 与 requirements_and_feasibility.md 第 9 章 Schema 定义对齐

## Unit Test
- `test_llm_config_defaults`: 验证 LLMConfig 默认值（provider="openai", temperature=0.7 等）
- `test_llm_config_validation`: temperature 超出 0-2 范围时抛出 ValidationError
- `test_paper_record_serialization`: PaperRecord JSON 序列化/反序列化往返一致
- `test_gap_item_fields`: GapItem 必填字段缺失时抛出 ValidationError
- `test_session_status_enum`: SessionStatus 枚举值正确
- `test_external_ids_optional`: ExternalIds 所有字段可为 None
- `test_gap_analysis_result_structure`: GapAnalysisResult 嵌套 SearchResult 正确解析
- `test_gap_analysis_result_full_papers`: GapAnalysisResult.papers 为完整 PaperRecord 列表（非仅 ID）
- `test_gap_analysis_result_full_matrix`: GapAnalysisResult.coverage_matrix 为完整 dict（非仅 summary）
