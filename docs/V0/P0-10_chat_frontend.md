# P0-10: Chat 前端页 + 流式消息

## 依赖
- P0-08（Next.js 项目骨架）
- P0-09（LLM 配置前端页）

## 目的
实现 QA Chat 前端页面，支持用户输入问题、接收 SSE 流式回答、展示带引用标注的消息，提供完整的聊天交互体验。

## 执行方法
1. 创建自定义 hook `hooks/useEventSource.ts`：
   - 封装 EventSource API，支持 chat_token / chat_done / error 事件
   - 管理连接生命周期（自动重连、断开清理）
   - 返回 {tokens, answer, citations, status, error}
2. 创建组件：
   - `components/chat/ChatWindow.tsx` — 聊天窗口容器（消息列表 + 输入框 + 发送按钮）
   - `components/chat/ChatMessage.tsx` — 单条消息（区分 user/assistant，assistant 消息支持引用高亮）
   - `components/chat/CitationPopover.tsx` — 引用弹出层（点击引用标注显示原文片段、来源、页码）
3. 在 `app/chat/page.tsx` 中集成：
   - 页面加载时获取当前会话的聊天历史
   - 用户输入问题 → POST /api/chat/ask → 获取 msg_id → 连接 SSE stream
   - 流式显示 token，完成后渲染完整消息 + 引用标注
   - 消息列表自动滚动到底部
4. 使用 SWR 获取聊天历史，useEventSource 处理流式数据

## 验收条件
- 用户输入问题后实时显示流式回答（逐 token）
- 回答完成后引用标注可点击，弹出原文片段
- 聊天历史正确加载和显示
- 消息区域自动滚动
- 发送中禁用输入框和发送按钮
- SSE 连接错误时显示错误提示

## Unit Test
- `test_chat_window_renders`: 验证 ChatWindow 包含消息列表和输入框
- `test_send_message`: 输入文本点击发送，验证 POST 请求发出
- `test_streaming_display`: mock SSE，验证 token 逐个追加显示
- `test_citation_popover`: 点击引用标注，验证 Popover 显示原文
- `test_chat_history_load`: mock API，验证历史消息正确渲染
- `test_input_disabled_during_stream`: 流式回答中输入框禁用
- `test_auto_scroll`: 新消息到达时滚动到底部
- `test_error_display`: SSE error 事件时显示错误提示
