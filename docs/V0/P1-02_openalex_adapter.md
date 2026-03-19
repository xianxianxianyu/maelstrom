# P1-02: OpenAlexAdapter

## 依赖
- P1-00（BaseAdapter 接口）

## 目的
实现 OpenAlex API 适配器，接入覆盖 2.5 亿+ 作品的开放元数据源，无需 API key，通过 mailto 参数进入 polite pool 获得更高限额。

## 执行方法
1. 在 `src/maelstrom/adapters/openalex_adapter.py` 中实现 `OpenAlexAdapter(BaseAdapter)`：
   - `source_name = "openalex"`
   - 使用 OpenAlex REST API（`https://api.openalex.org/works`）
   - 查询参数：search, filter, per_page, mailto
   - 请求字段：title, abstract_inverted_index, authorships, publication_year, primary_location, doi, ids, cited_by_count
2. `normalize` 实现：
   - abstract_inverted_index → 还原为纯文本 abstract
   - authorships → [{name, affiliation}] 格式
   - ids.openalex → external_ids.openalex_id
   - primary_location.source.display_name → venue
   - doi 提取（去除 https://doi.org/ 前缀）
3. 速率限制：10 req/s（polite pool 需 mailto 参数）
4. 超时：10s per request

## 验收条件
- 搜索返回归一化的 PaperRecord 列表
- abstract_inverted_index 正确还原为文本
- external_ids 包含 openalex_id 和可用的 DOI
- mailto 参数正确附加到请求
- 超时正确处理

## Unit Test
- `test_openalex_search_mock`: mock API，验证搜索返回正确结果
- `test_openalex_normalize`: 验证响应正确映射到 PaperRecord
- `test_openalex_abstract_restore`: 验证 abstract_inverted_index 正确还原为文本
- `test_openalex_doi_extraction`: 验证 DOI 去除前缀后正确映射
- `test_openalex_mailto`: 验证请求包含 mailto 参数
- `test_openalex_timeout`: mock 超时，验证异常处理
- `test_openalex_empty_abstract`: abstract_inverted_index 为空时 abstract 为空字符串
