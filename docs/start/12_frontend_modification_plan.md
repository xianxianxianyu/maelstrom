# Maelstrom 前端修改计划 — assistant-ui 集成

## 1. 集成策略

用 `assistant-ui` 替换当前手写的聊天层，保留 Gap/Synthesis/Planning/Experiment 等独立工作台页面不变。

核心映射关系：

| Maelstrom 概念 | assistant-ui 概念 |
|---|---|
| Session | Thread |
| `/api/sessions` CRUD | RemoteThreadListAdapter |
| `/api/router/input/stream` SSE | ChatModelAdapter.run() |
| Gap/Citation/Clarification 结构化结果 | makeAssistantToolUI |
| `useConversation` reducer | 由 assistant-ui runtime 接管 |
| `useUnifiedStream` | 由 ChatModelAdapter 的 AsyncGenerator 接管 |
| `MessageList` + 各种 Bubble | assistant-ui 的 Thread + Message 原语 |
| `UnifiedInputBar` | assistant-ui 的 Composer 原语 |
| `DocUploader` / `DocDrawer` | 保留，作为 Composer attachments 扩展 |

选用 **LocalRuntime + ChatModelAdapter** 方案，原因：
- Maelstrom 的聊天是"用户发消息 → 后端 SSE 流式回复"的标准模式，ChatModelAdapter 完美匹配
- LocalRuntime 自动管理消息状态、分支、重载，省掉 `useConversation` 的 reducer
- 通过 `adapters.threadList` 接入 RemoteThreadListAdapter，实现 session 列表同步

---

## 2. 任务清单

### Task 1: 安装 assistant-ui 依赖

方案：
- 安装 `@assistant-ui/react`（核心包，含原语 + runtime）
- 安装 `@assistant-ui/react-markdown`（Markdown 渲染，替换当前 react-markdown）
- 用 `npx assistant-ui add thread` 生成 shadcn 风格的 Thread 组件到 `src/components/ui/assistant-ui/`
- 不安装 `@assistant-ui/react-ai-sdk`（我们用自定义后端，不用 Vercel AI SDK）
- 不安装 `@assistant-ui/cloud`（持久化由 Maelstrom 后端负责）

涉及文件：
- `package.json`
- `src/components/ui/assistant-ui/thread.tsx`（新增，由 CLI 生成）

---

### Task 2: 实现 MaelstromChatAdapter（ChatModelAdapter）

方案：

创建 `src/lib/maelstrom-chat-adapter.ts`，实现 `ChatModelAdapter` 接口。

核心逻辑：
```
run({ messages, abortSignal, context }) → AsyncGenerator<ChatModelRunResult>
```

1. 取最后一条 user message 的 text content 作为 question
2. POST `/api/router/input/stream`，body: `{ session_id, input: question }`
3. 读取 SSE 流，按事件类型映射：
   - `route_resolved` → 忽略（内部路由信息）
   - `chat_token` → yield `{ content: [{ type: "text", text: accumulated }] }`
   - `chat_done` → yield 最终结果，附带 citations 作为 tool call result
   - `step_start` / `step_complete` / `papers_found` / `matrix_ready` / `gap_found` → yield 为 tool call part（GapRun 工具），实时更新 args
   - `result`（gap 完成）→ yield 为 GapRun tool call 的 result
   - `clarification` → yield 为 Clarification tool call（需要用户 addResult）
   - `error` → throw

关键设计：
- Gap 运行在聊天中表现为一个 tool call `gap_analysis`，其 UI 由 makeAssistantToolUI 渲染
- Clarification 表现为一个 tool call `clarification`，用户选择后通过 addResult 回传
- Citations 表现为 SourceMessagePart，assistant-ui 原生支持

涉及文件：
- `src/lib/maelstrom-chat-adapter.ts`（新增）

---

### Task 3: 实现 RemoteThreadListAdapter（Session 列表）

方案：

创建 `src/lib/maelstrom-thread-list-adapter.ts`，实现 `RemoteThreadListAdapter` 接口。

映射：
- `list()` → GET `/api/sessions`，转换为 `{ threads: [{ remoteId, title, status }] }`
- `initialize(threadId)` → POST `/api/sessions`，返回新 session 的 remoteId
- `rename(remoteId, newTitle)` → PUT `/api/sessions/{remoteId}`（需要后端补这个接口，或暂时 no-op）
- `archive(remoteId)` → DELETE `/api/sessions/{remoteId}`
- `delete(remoteId)` → DELETE `/api/sessions/{remoteId}`
- `generateTitle(remoteId, messages)` → 返回空流（V0 不自动生成标题）

线程历史持久化（ThreadHistoryAdapter）：
- `load(threadId)` → GET `/api/chat/messages?session_id={threadId}`，转换为 ThreadMessageLike[]
- 不需要 `save()`，消息由后端在 ask 时自动持久化

涉及文件：
- `src/lib/maelstrom-thread-list-adapter.ts`（新增）

---

### Task 4: 创建 AssistantProvider 顶层包装

方案：

创建 `src/components/providers/AssistantProvider.tsx`，组装 runtime 并提供给整个应用。

```tsx
// 伪代码
const adapter = new MaelstromChatAdapter();
const threadListAdapter = new MaelstromThreadListAdapter();
const runtime = useRemoteThreadListRuntime({
  runtimeHook: () => useLocalRuntime(adapter),
  adapter: threadListAdapter,
});
return <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>;
```

在 `layout.tsx` 中包裹整个应用，使所有页面都能访问 runtime context。

涉及文件：
- `src/components/providers/AssistantProvider.tsx`（新增）
- `src/app/layout.tsx`（修改，包裹 AssistantProvider）

---

### Task 5: 注册 Tool UI 组件

方案：

创建 `src/components/tools/` 目录，为每种结构化结果注册 Tool UI。

**5a. GapAnalysisToolUI**

```tsx
const GapAnalysisToolUI = makeAssistantToolUI<GapToolArgs, GapToolResult>({
  toolName: "gap_analysis",
  render: ({ args, result, status }) => {
    // status.type === "running" 时：显示 RunProgress + 实时更新的 papers/matrix/gaps
    // status.type === "complete" 时：显示完整的 GapList + TopicCandidateCard + CoverageMatrix
    // 复用现有的 RunProgress, PaperList, CoverageMatrix, GapList, TopicCandidateCard 组件
  },
});
```

args 结构（运行中实时更新）：
```ts
type GapToolArgs = {
  topic: string;
  currentStep?: string;
  papers?: PaperRecord[];
  matrix?: CoverageMatrix;
  gaps?: GapItem[];
};
```

result 结构（运行完成）：
```ts
type GapToolResult = {
  papers: PaperRecord[];
  matrix: CoverageMatrix;
  gaps: GapItem[];
  candidates: TopicCandidate[];
  runId: string;
};
```

**5b. ClarificationToolUI**

```tsx
const ClarificationToolUI = makeAssistantToolUI<ClarificationArgs, ClarificationResult>({
  toolName: "clarification",
  render: ({ args, addResult, status }) => {
    // 显示问题 + 选项按钮
    // 用户点击后调用 addResult({ choice: selectedOption })
    // 复用现有 ClarificationCard 组件，改造为调用 addResult
  },
});
```

**5c. CitationToolUI**（可选，也可以用 SourceMessagePart）

如果 citations 作为 tool call 返回，注册对应 UI。但更推荐把 citations 映射为 assistant-ui 的 `SourceMessagePart`，这样可以用原生的 source 展示。

涉及文件：
- `src/components/tools/GapAnalysisToolUI.tsx`（新增）
- `src/components/tools/ClarificationToolUI.tsx`（新增）
- `src/components/tools/index.tsx`（新增，统一注册）

---

### Task 6: 重写 Chat 页面

方案：

用 assistant-ui 原语重写 `src/app/chat/page.tsx`。

当前 chat/page.tsx 的职责：
1. useSession 管理 session → 改为 assistant-ui 的 thread context
2. useConversation 管理消息 → 删除，由 runtime 接管
3. useUnifiedStream 处理 SSE → 删除，由 ChatModelAdapter 接管
4. 加载历史消息 → 由 ThreadHistoryAdapter 接管
5. 渲染 MessageList → 改为 assistant-ui 的 Thread 组件
6. 渲染 UnifiedInputBar → 改为 assistant-ui 的 Composer
7. 渲染 ChatHeader → 保留，微调
8. 渲染 DocDrawer → 保留，作为侧边面板

新的 chat/page.tsx 结构：
```tsx
<div className="flex h-full">
  <div className="flex-1 flex flex-col">
    <ChatHeader />
    <Thread>
      {/* assistant-ui 自动渲染消息列表 */}
      {/* GapAnalysisToolUI 和 ClarificationToolUI 自动在 tool call 处渲染 */}
    </Thread>
  </div>
  {showDocs && <DocDrawer />}
</div>
```

需要自定义的 Message 渲染：
- User message：保留当前 UserBubble 的样式，通过 MessagePrimitive 自定义
- Assistant text：用 @assistant-ui/react-markdown 渲染，附带 CitationPopover
- System notice：通过 MessagePrimitive.If 条件渲染
- IntentBadge：作为 assistant message 的 header 部分

涉及文件：
- `src/app/chat/page.tsx`（重写）
- `src/components/chat/ChatMessage.tsx`（删除，被原语替代）
- `src/components/chat/MessageList.tsx`（删除，被 Thread 替代）
- `src/components/chat/UnifiedInputBar.tsx`（删除，被 Composer 替代）
- `src/components/chat/TextBubble.tsx`（改造为 assistant-ui Message 自定义渲染）
- `src/components/chat/UserBubble.tsx`（改造为 assistant-ui Message 自定义渲染）
- `src/components/chat/GapRunBlock.tsx`（删除，被 GapAnalysisToolUI 替代）
- `src/components/chat/ClarificationCard.tsx`（改造，接入 addResult）
- `src/components/chat/SystemNotice.tsx`（保留，作为自定义 message part）
- `src/components/chat/IntentBadge.tsx`（保留）
- `src/components/chat/CitationPopover.tsx`（保留）
- `src/components/chat/ChatHeader.tsx`（保留，微调）
- `src/components/chat/DocDrawer.tsx`（保留）
- `src/components/chat/DocUploader.tsx`（保留）

---

### Task 7: 重写 Session 侧边栏 / 列表

方案：

用 assistant-ui 的 ThreadListPrimitive 替换当前 Sidebar 中的 session 显示和 `/sessions` 页面。

**Sidebar 改造：**

当前 Sidebar 底部显示当前 session 标题。改为：
- 用 ThreadListPrimitive 渲染 session 列表（折叠式，在侧边栏内）
- 点击切换 thread（即切换 session）
- 新建 session 按钮

**Sessions 页面改造：**

当前 `/sessions` 是独立的 session 管理页。改为：
- 用 ThreadListPrimitive 渲染完整列表
- 保留 phase badge、status badge、运行数等元数据展示
- 保留删除功能

涉及文件：
- `src/components/layout/Sidebar.tsx`（修改）
- `src/app/sessions/page.tsx`（修改）

---

### Task 8: 清理废弃的 hooks 和组件

方案：

以下 hooks 被 assistant-ui runtime 替代，应删除：
- `src/hooks/useConversation.ts` → runtime 管理消息状态
- `src/hooks/useUnifiedStream.ts` → ChatModelAdapter 管理流
- `src/hooks/useEventSource.ts` → 不再需要（旧版 ChatWindow 用的）
- `src/hooks/useRouter.ts` → 不再需要（旧版 ChatWindow 用的）
- `src/hooks/useSession.ts` → 被 thread context 替代（但 Gap/Synthesis 等页面可能仍需要，保留并评估）

以下组件被替代，应删除：
- `src/components/chat/ChatWindow.tsx` → 旧版聊天窗口，已被 chat/page.tsx 替代，现在进一步被 Thread 替代
- `src/types/conversation.ts` → 消息类型由 assistant-ui 的 ThreadMessage 替代（但 GapItem/PaperRecord 等业务类型需保留，迁移到新文件）

涉及文件：
- 上述文件删除或迁移

---

### Task 9: PDF 上传集成到 Composer Attachments

方案：

当前 PDF 上传有两个入口：
1. DocDrawer 中的 DocUploader（显式管理）
2. chat/page.tsx 中的拖拽上传

改造为：
- 保留 DocDrawer 作为文档管理面板（查看已上传文档、删除）
- 将拖拽上传集成到 Composer 的 attachment 机制
- 用户拖拽 PDF 到输入框 → 显示为 attachment → 发送时自动上传到 `/api/chat/docs/upload`
- 通过 LocalRuntime 的 `adapters.attachments` 实现自定义 attachment 处理

涉及文件：
- `src/lib/maelstrom-attachment-adapter.ts`（新增）
- `src/components/chat/DocDrawer.tsx`（保留，微调）

---

### Task 10: 错误处理与 Toast 通知

方案：

- 安装 sonner（shadcn/ui 推荐的 toast 库）或使用 shadcn 的 toast 组件
- 在 ChatModelAdapter 中捕获 SSE 错误，通过 assistant-ui 的 error 机制展示
- LLM API key 无效 → adapter 抛错 → assistant-ui 显示 error message
- PDF 上传失败 → DocUploader 内 toast 提示
- Gap 运行失败 → GapAnalysisToolUI 的 status.type === "error" 分支渲染错误卡片

涉及文件：
- `src/app/layout.tsx`（添加 Toaster）
- `src/lib/maelstrom-chat-adapter.ts`（错误处理）
- `src/components/tools/GapAnalysisToolUI.tsx`（错误状态渲染）

---

### Task 11: 响应式布局优化

方案：

- Sidebar：窄屏（<768px）下默认折叠，hamburger 按钮展开
- Thread：全宽，自动适配
- DocDrawer：窄屏下改为 bottom sheet 或 modal
- CoverageMatrix：添加 `overflow-x-auto` 横向滚动
- GapCard/TopicCandidateCard：窄屏下单列堆叠

涉及文件：
- `src/components/layout/Sidebar.tsx`（响应式折叠）
- `src/components/chat/DocDrawer.tsx`（响应式适配）
- `src/components/gap/CoverageMatrix.tsx`（横向滚动）

---

## 3. 执行顺序

```
Phase 1: 基础设施（Task 1 → 4）
  安装依赖 → 实现 Adapter → 实现 ThreadList → 创建 Provider
  预计：可并行，1 轮完成

Phase 2: Tool UI（Task 5）
  注册 GapAnalysis / Clarification 的 Tool UI
  依赖 Phase 1 完成

Phase 3: 页面重写（Task 6 → 7）
  重写 Chat 页面 → 重写 Session 列表
  依赖 Phase 2 完成

Phase 4: 清理与增强（Task 8 → 11）
  清理废弃代码 → PDF attachment → 错误处理 → 响应式
  依赖 Phase 3 完成
```

---

## 4. 不动的部分

以下页面和组件不在本次修改范围内：

- `/gap` 页面及其组件（TopicInput, RunProgress, GapCard 等）— 独立工作台，不走 chat
- `/synthesis` 页面及其组件 — 同上
- `/planning` 页面及其组件 — 同上
- `/experiment` 页面及其组件 — 同上
- `/workspace` 页面及其组件 — 同上
- `/reports/[id]` 页面 — 同上
- `/settings` 页面 — 同上
- `useGapStream` / `useSynthesisStream` / `usePlanningStream` / `useExperimentStream` — 这些是独立引擎页面的 SSE hooks，不受 chat 层改造影响
- 所有后端代码 — 本次只改前端
