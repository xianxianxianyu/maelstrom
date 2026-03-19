# P2-09: 前端 Router SSE 适配 + 意图指示器

## 依赖
- P2-05（Phase Router 前端集成 — useRouter）
- P2-08（Router SSE 协议 — /api/router/input/stream）

## 目的
将前端从 P2-05 的 JSON 请求/响应模式升级为 SSE 流模式，接入 `/api/router/input/stream`。新增意图指示器组件，让用户实时看到系统的分类结果和处理进度。

## 执行方法

### 1. Hook 升级 — `frontend/src/hooks/useRouter.ts`

从 fetch JSON 改为 EventSource 消费：
```typescript
function useRouterStream(sessionId: string) {
  const [intent, setIntent] = useState<string | null>(null);
  const [phase, setPhase] = useState<"routing" | "streaming" | "done" | "error">("routing");
  const [clarification, setClarification] = useState<ClarificationRequest | null>(null);
  const [redirectPath, setRedirectPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 内部维护一个 EventSource 连接
  // 事件处理：
  // route_resolved → setIntent, setPhase("streaming")
  // clarification → setClarification, setPhase("done")
  // redirect → setRedirectPath, setPhase("done")
  // error → setError, setPhase("error")
  // chat_token / step_start / papers_found / ... → 透传给子组件
  // __done__ → setPhase("done"), 关闭连接

  async function sendInput(input: string) { ... }
  async function replyClarification(...) { ... }

  return { intent, phase, clarification, redirectPath, error, sendInput, replyClarification, ... };
}
```

### 2. 意图指示器 — `frontend/src/components/chat/IntentBadge.tsx`

在 Chat 消息流中，路由完成后显示一个小标签：
- `gap_discovery` → 蓝色标签 "🔍 研究缺口分析"
- `qa_chat` → 绿色标签 "💬 文档问答"
- `gap_followup` → 紫色标签 "📎 Gap 追问"
- `clarification_needed` → 黄色标签 "❓ 需要澄清"

使用 shadcn/ui Badge 组件，带 tooltip 显示 confidence 值。

路由中（phase="routing"）时显示加载动画："正在理解你的意图..."

### 3. ChatWindow 适配

```typescript
// 替换 P2-05 的 fetch 逻辑为 SSE 流
const { intent, phase, clarification, ... } = useRouterStream(sessionId);

// 路由中 → 显示 IntentBadge loading
// 路由完成 → 显示 IntentBadge + 对应内容
// chat 流 → 复用现有 ChatMessage 渲染
// gap 流 → 嵌入 RunProgress 卡片或跳转
// clarification → 渲染 ClarificationCard
```

### 4. Gap 流内嵌模式

当 gap_discovery 在 Chat 页面触发时，不强制跳转到 /gap 页面，而是在 Chat 中内嵌一个精简版进度卡片：
- 显示当前步骤（"正在检索论文..." / "正在分析覆盖矩阵..."）
- 完成后显示摘要卡片（N 篇论文, M 个 gap）
- 卡片底部有 "查看完整结果" 链接跳转到 /gap

## 验收条件
- Chat 页面通过 SSE 接入 Phase Router
- 路由中显示加载动画
- 路由完成后显示意图标签（IntentBadge）
- chat 流正常渲染消息
- gap 流在 Chat 中显示内嵌进度卡片
- clarification 正常渲染反问卡片
- redirect 正常跳转
- error 显示错误提示
- __done__ 后连接正确关闭

## Unit Test（vitest）
- `test_useRouterStream_route_resolved`: route_resolved 事件 → intent 状态更新
- `test_useRouterStream_clarification`: clarification 事件 → clarification 状态更新
- `test_useRouterStream_done`: __done__ 事件 → phase="done"
- `test_IntentBadge_gap`: intent="gap_discovery" → 蓝色标签
- `test_IntentBadge_qa`: intent="qa_chat" → 绿色标签
- `test_IntentBadge_loading`: phase="routing" → 加载动画
- `test_gap_inline_card`: gap 流事件 → 渲染进度卡片 + "查看完整结果" 链接
