# P0-05: paper-qa 封装层

## 依赖
- P0-01（Pydantic Schema — LLMConfig）
- P0-03（LLM 配置 API）

## 目的
封装 paper-qa 库，隔离其 API 变动风险，实现 LLM 配置动态透传，为 QA Chat 和 Gap Engine 提供统一的文档索引与问答接口。

## 执行方法
1. 在 `src/maelstrom/services/paperqa_service.py` 中实现：
   - `PaperQAService` 类：
     - `build_settings(llm_config: LLMConfig) -> Settings` — 根据当前 LLM 配置动态构造 paper-qa Settings
     - `index_document(file_path: str, settings: Settings) -> str` — 索引单个 PDF，返回 doc_id
     - `ask(question: str, doc_ids: list[str], settings: Settings) -> AsyncGenerator` — 流式问答，yield token
     - `list_docs() -> list[dict]` — 列出已索引文档
     - `remove_doc(doc_id: str) -> bool` — 移除文档索引
2. Settings 构造逻辑：
   - provider → 对应 LLM client（openai / anthropic / local）
   - api_key, base_url, temperature, max_tokens 透传
   - embedding_model 透传到 paper-qa embedding 配置
3. 每次调用时重新构造 Settings，不缓存，确保配置变更即时生效
4. 异常处理：paper-qa 异常统一转换为自定义 `PaperQAError`

## 验收条件
- `build_settings` 正确映射 LLMConfig 到 paper-qa Settings
- `index_document` 可索引有效 PDF 文件
- `ask` 返回流式 token 和最终带引用的回答
- LLM 配置变更后下次调用使用新配置
- paper-qa 异常被正确捕获和转换

## Unit Test
- `test_build_settings_openai`: OpenAI provider 配置正确映射
- `test_build_settings_anthropic`: Anthropic provider 配置正确映射
- `test_build_settings_local`: local provider 配置含 base_url
- `test_settings_no_cache`: 修改 LLMConfig 后 build_settings 返回新 Settings
- `test_index_document_mock`: mock paper-qa，验证 index_document 调用参数正确
- `test_ask_streaming_mock`: mock paper-qa，验证 ask 返回 AsyncGenerator
- `test_paperqa_error_handling`: paper-qa 抛异常时转换为 PaperQAError
