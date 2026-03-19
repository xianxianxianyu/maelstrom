# P1-00: BaseAdapter 接口 + ArxivAdapter

## 依赖
- P0-01（Pydantic Schema — PaperRecord）

## 目的
定义论文检索适配器的抽象基类 `BaseAdapter`，并实现第一个适配器 `ArxivAdapter`，为四源并行检索奠定基础。

## 执行方法
1. 在 `src/maelstrom/adapters/base.py` 中定义：
   - `RawPaperResult` — 适配器原始返回的中间数据结构
   - `BaseAdapter(ABC)` 抽象基类：
     - `source_name: str` 属性
     - `async search(query: str, max_results: int) -> list[RawPaperResult]` 抽象方法
     - `normalize(raw: RawPaperResult) -> PaperRecord` 抽象方法
2. 在 `src/maelstrom/adapters/arxiv_adapter.py` 中实现 `ArxivAdapter`：
   - 使用 `arxiv` Python 包或直接调用 arXiv REST API
   - 速率限制：3 req/s（礼貌限制）
   - `search`: 查询 arXiv，返回 RawPaperResult 列表
   - `normalize`: 转换为 PaperRecord（标题 strip HTML + NFC 规范化，作者格式化，日期 ISO 8601，arxiv_id 映射到 external_ids）
3. 超时处理：单次请求 10s 超时
4. 使用 httpx AsyncClient

## 验收条件
- `BaseAdapter` 不可直接实例化（ABC）
- `ArxivAdapter` 可正常搜索并返回 PaperRecord 列表
- 归一化后的 PaperRecord 字段完整（title, authors, abstract, year, external_ids.arxiv_id）
- 速率限制生效（不超过 3 req/s）
- 超时时抛出明确异常而非挂起

## Unit Test
- `test_base_adapter_abstract`: 直接实例化 BaseAdapter 抛出 TypeError
- `test_arxiv_search_mock`: mock arXiv API，验证 search 返回正确数量的结果
- `test_arxiv_normalize`: 给定 RawPaperResult，验证 normalize 输出 PaperRecord 字段正确
- `test_arxiv_title_normalization`: 验证 HTML 标签被 strip，Unicode NFC 规范化
- `test_arxiv_date_format`: 验证日期转换为 ISO 8601 格式
- `test_arxiv_timeout`: mock 超时响应，验证抛出超时异常
- `test_arxiv_empty_results`: 查询无结果时返回空列表
