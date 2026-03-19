# P0-07: QA Chat API + SSE 流式

## 依赖
- P0-05（paper-qa 封装层）
- P0-06（PDF 上传 + 索引 API）

## 目的
实现 QA Chat 的核心问答 API，支持 SSE 流式回答，集成 LangGraph QA 子图，返回带引用的回答。

## 执行方法
1. 在 `src/maelstrom/graph/qa_chat.py` 中定义 LangGraph QA 子图：
   - `QAChatState` TypedDict（question, llm_config, session_id, indexed_docs, retrieved_chunks, answer, citations, error）
   - 4 个节点：receive_question → retrieve_chunks → generate_answer → format_citations
   - 使用 paper-qa 进行 chunk 检索和回答生成
2. 在 `src/maelstrom/api/chat.py` 中实现路由：
   - `POST /api/chat/ask` — 接收 {question, session_id}，启动 QA 子图，返回 msg_id
   - `GET /api/chat/ask/{msg_id}/stream` — SSE 流式推送（chat_token + chat_done 事件）
3. SSE 事件格式：
   - `chat_token`: `{token: str}` — 逐 token 推送
   - `chat_done`: `{answer: str, citations: [{text, source, page}]}` — 完成事件
   - `error`: `{message: str}` — 错误事件
4. 聊天记录写入 SQLite chat_messages 表
5. 使用 `sse-starlette` 的 `EventSourceResponse`

## 验收条件
- POST /api/chat/ask 返回 202 + msg_id
- SSE stream 正确推送 chat_token 事件（逐 token）
- 最终 chat_done 事件包含完整 answer 和 citations
- citations 可追溯到具体 PDF 页码/段落
- 聊天记录持久化到 SQLite
- 无已索引文档时返回明确错误提示
- SSE 连接断开时资源正确清理

## Unit Test
- `test_ask_returns_msg_id`: POST 问题返回 202 + msg_id
- `test_sse_stream_tokens`: mock paper-qa，验证 SSE 推送 chat_token 事件
- `test_sse_stream_done`: 验证最终 chat_done 事件包含 answer 和 citations
- `test_chat_message_persisted`: 问答完成后验证 chat_messages 表有记录
- `test_ask_no_docs`: 无索引文档时返回错误提示
- `test_ask_invalid_session`: 不存在的 session_id 返回 404
- `test_qa_graph_nodes`: 验证 QA 子图 4 个节点按序执行
- `test_sse_error_event`: paper-qa 异常时推送 error 事件
