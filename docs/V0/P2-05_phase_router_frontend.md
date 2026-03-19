# P2-05: Phase Router 前端集成

## 依赖
- P2-03（Phase Router API — /api/router/input）
- P2-04（统一 Chat 入口 + /api/chat/clarify）
- P1-13（Gap Engine 前端 — useGapStream）
- P0-10（Chat 前端 — ChatWindow）

## 目的
改造前端 Chat 页面，接入 Phase Router 统一入口。用户在 Chat 输入框输入任何内容，前端调用 `/api/router/input`，根据返回的 `response_type` 自动处理：流式展示、反问交互、或页面跳转。

## 执行方法

### 1. 新增 Hook — `frontend/src/hooks/useRouter.ts`

```typescript
interface RouterResponse {
  response_type: "stream" | "clarification" | "redirect" | "error";
  stream_url?: string;
  clarification?: ClarificationRequest;
  redirect_path?: string;
  error_message?: string;
}

interface ClarificationRequest {
  request_id: string;
  question: string;
  options: { label: string; intent: string; description: string }[];
  allow_freetext: boolean;
  original_input: string;
  session_id: string;
}

function useRouter(sessionId: string) {
  const [pending, setPending] = useState(false);
  const [clarification, setClarification] = useState<ClarificationRequest | null>(null);

  async function sendInput(input: string): Promise<RouterResponse> { ... }
  async function replyClarification(requestId: string, optionIndex?: number, freetext?: string): Promise<RouterResponse> { ... }

  return { sendInput, replyClarification, pending, clarification };
}
```

### 2. 反问 UI 组件 — `frontend/src/components/chat/ClarificationCard.tsx`

当 `response_type === "clarification"` 时渲染：
- 显示反问文本（`question`）
- 渲染选项按钮列表（`options`）
- 如果 `allow_freetext`，显示文本输入框
- 用户点击选项 → 调用 `replyClarification(request_id, option_index)`
- 用户提交自由文本 → 调用 `replyClarification(request_id, undefined, freetext)`

样式：使用 shadcn/ui Card + Button 组件，与现有 ChatMessage 风格一致。

### 3. ChatWindow 改造 — `frontend/src/components/chat/ChatWindow.tsx`

修改消息发送逻辑：
```typescript
// Before (P0):
// const { msgId } = await fetch("/api/chat/ask", { body: { session_id, question } });
// subscribe to /api/chat/ask/{msgId}/stream

// After (P2):
const response = await sendInput(userInput);

switch (response.response_type) {
  case "stream":
    // 根据 stream_url 判断是 chat 还是 gap
    if (response.stream_url.includes("/api/chat/")) {
      subscribeToChat(response.stream_url);
    } else if (response.stream_url.includes("/api/gap/")) {
      // 在 chat 中嵌入 gap 进度卡片，或跳转到 gap 页面
      router.push(`/gap?stream=${encodeURIComponent(response.stream_url)}`);
    }
    break;
  case "clarification":
    setClarification(response.clarification);
    break;
  case "redirect":
    router.push(response.redirect_path);
    break;
  case "error":
    showError(response.error_message);
    break;
}
```

### 4. Chat 消息列表中的反问消息

反问作为一种特殊的 assistant 消息渲染在聊天流中：
- 类型标记：`message.type === "clarification"`
- 渲染 `ClarificationCard` 而非普通文本
- 用户回复后，ClarificationCard 变为已回答状态（灰色，显示用户选择）

## 验收条件
- Chat 输入框发送消息后调用 `/api/router/input`
- gap_discovery 意图 → 跳转到 Gap 页面并开始流式展示
- qa_chat 意图 → 在 Chat 中流式展示回答
- clarification → 在 Chat 中渲染 ClarificationCard
- 用户点击选项 → 调用 /api/chat/clarify → 正确路由
- config/share_to_qa → 页面跳转
- 原有 Chat 功能不受影响（直接问答仍可用）

## Unit Test（vitest）
- `test_useRouter_sendInput`: mock fetch → 返回 RouterResponse
- `test_useRouter_clarification`: response_type=clarification → clarification state 更新
- `test_ClarificationCard_render`: 渲染选项按钮 + 自由输入框
- `test_ClarificationCard_option_click`: 点击选项 → 调用 replyClarification
- `test_ClarificationCard_freetext_submit`: 提交文本 → 调用 replyClarification
- `test_ChatWindow_stream_routing`: stream response → 订阅 SSE
- `test_ChatWindow_redirect`: redirect response → router.push 调用
