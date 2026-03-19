# P1-01: SemanticScholarAdapter

## 依赖
- P1-00（BaseAdapter 接口）

## 目的
实现 Semantic Scholar API 适配器，接入 S2 的论文检索和引用网络数据，支持可选 API key 提升限额。

## 执行方法
1. 在 `src/maelstrom/adapters/s2_adapter.py` 中实现 `SemanticScholarAdapter(BaseAdapter)`：
   - `source_name = "s2"`
   - 使用 Semantic Scholar Academic Graph API（`https://api.semanticscholar.org/graph/v1/paper/search`）
   - 请求字段：title, abstract, authors, year, venue, externalIds, citationCount, openAccessPdf
   - 支持可选 API key（通过 header `x-api-key`）
   - 速率限制：100 req/5min（无 key），更高（有 key）
2. `normalize` 实现：
   - S2 externalIds 映射到 PaperRecord.external_ids（DOI, ArXiv, CorpusId）
   - authors 格式化为 [{name, affiliation}]
   - openAccessPdf.url 映射到 pdf_url
3. 超时：10s per request
4. 支持 batch API（`POST /paper/batch`）用于批量获取详情

## 验收条件
- 搜索返回归一化的 PaperRecord 列表
- external_ids 包含 s2_id 和可用的 DOI/ArXiv ID
- 有/无 API key 均可工作
- 速率限制不被触发（正常使用场景）
- 超时正确处理

## Unit Test
- `test_s2_search_mock`: mock S2 API，验证搜索返回正确结果
- `test_s2_normalize`: 验证 S2 响应正确映射到 PaperRecord
- `test_s2_external_ids`: 验证 externalIds 正确映射（DOI, ArXiv, CorpusId → external_ids）
- `test_s2_with_api_key`: 验证有 API key 时 header 正确设置
- `test_s2_without_api_key`: 验证无 API key 时正常工作
- `test_s2_pdf_url`: 验证 openAccessPdf.url 映射到 pdf_url
- `test_s2_timeout`: mock 超时，验证异常处理
