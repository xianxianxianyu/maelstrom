# P1-03: OpenReviewAdapter

## 依赖
- P1-00（BaseAdapter 接口）

## 目的
实现 OpenReview API v2 适配器，接入顶会论文数据（ICLR/NeurIPS/ICML），补充其他源缺少的同行评审论文。

## 执行方法
1. 在 `src/maelstrom/adapters/openreview_adapter.py` 中实现 `OpenReviewAdapter(BaseAdapter)`：
   - `source_name = "openreview"`
   - 使用 OpenReview API v2（`https://api2.openreview.net/notes/search`）
   - 查询参数：query, limit, offset
   - 响应字段：id, content.title, content.abstract, content.authors, content.venue, content.pdf
2. `normalize` 实现：
   - content.title.value → title
   - content.authors.value → authors [{name}]（OpenReview 通常无 affiliation）
   - content.venue.value → venue
   - id → external_ids.openreview_id
   - content.pdf → pdf_url（拼接 OpenReview 域名）
3. 分页处理：offset + limit 遍历
4. 超时：10s per request
5. 注意：OpenReview API 文档不完善，需实测验证响应格式

## 验收条件
- 搜索返回归一化的 PaperRecord 列表
- external_ids 包含 openreview_id
- venue 正确提取（如 "ICLR 2024"）
- pdf_url 可用
- API 不可用时优雅降级（不阻塞其他源）

## Unit Test
- `test_openreview_search_mock`: mock API，验证搜索返回正确结果
- `test_openreview_normalize`: 验证响应正确映射到 PaperRecord
- `test_openreview_venue`: 验证 venue 正确提取
- `test_openreview_pdf_url`: 验证 pdf_url 正确拼接
- `test_openreview_pagination`: mock 分页响应，验证多页结果合并
- `test_openreview_timeout`: mock 超时，验证异常处理
- `test_openreview_api_error`: mock 500 响应，验证优雅降级
