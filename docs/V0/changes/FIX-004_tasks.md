# FIX-004 Tasks — Session 生命周期与运行恢复

> 对应文档：`docs/V0/changes/FIX-004_session_lifecycle_and_resume.md`
> 方案：渐进式增强（三步走）

---

## Step 1 — Session 可见化

### T1.1 后端：session_repo 新增 touch_session
- [x] 在 `src/maelstrom/db/session_repo.py` 新增 `touch_session(db, session_id)` 方法
- 仅执行 `UPDATE sessions SET updated_at = ? WHERE id = ?`
- 不需要返回值，静默失败即可（session 不存在时不报错）

### T1.2 后端：gap_run_repo 触发 session touch
- [x] `src/maelstrom/db/gap_run_repo.py` 的 `create_gap_run` 在 INSERT 后调用 `session_repo.touch_session(db, session_id)`
- [x] `update_gap_run_status` 在 UPDATE 后调用 `session_repo.touch_session(db, session_id)`

### T1.3 后端：chat_repo 触发 session touch
- [x] `src/maelstrom/db/chat_repo.py` 的 `create_chat_message` 在 INSERT 后调用 `session_repo.touch_session(db, session_id)`

### T1.4 后端：gap_run_repo 新增聚合查询
- [x] 新增 `count_by_session(db, session_id) -> int`
- [x] 新增 `latest_by_session(db, session_id) -> dict | None`

### T1.5 后端：chat_repo 新增聚合查询
- [x] 新增 `count_by_session(db, session_id) -> int`

### T1.6 后端：session 列表 API 返回聚合摘要
- [x] 修改 `src/maelstrom/api/sessions.py` 的 `list_sessions` 端点，返回聚合字段
- [x] 修改 `src/maelstrom/api/session_models.py` 的 `SessionResponse`，新增 run_count/latest_run_status/latest_run_topic/message_count

### T1.7 前端：Sessions 页面完整重写
- [x] 替换 `frontend/src/app/sessions/page.tsx` 占位内容
- [x] 页面 mount 时调用 `GET /api/sessions` 获取列表
- [x] 渲染 session 卡片（title、updated_at、run_count、latest_run_status、message_count）
- [x] "New Session" 按钮 + "Delete" 按钮
- [x] 点击跳转 `/gap?session_id=xxx` 或 `/chat?session_id=xxx`
- [x] 空状态提示

### T1.8 验证 Step 1
- [x] 创建 session → 列表中出现
- [x] 从 session 进入 Gap 并发起 run → 回到 Sessions 页面，该 session 的 updated_at 已刷新，run_count = 1
- [x] 从 session 进入 Chat 并发送消息 → 回到 Sessions 页面，message_count 增加
- [x] 删除 session → 列表中消失

---

## Step 2 — Gap 运行恢复

### T2.1 后端：gap_run_repo 新增 list_by_session
- [x] 新增 `list_by_session(db, session_id, limit=10) -> list[dict]`

### T2.2 后端：Gap API 新增按 session 查询 runs 端点
- [x] 在 `src/maelstrom/api/gap.py` 新增 `GET /api/gap/runs`

### T2.3 前端：useSession 支持 URL search params
- [x] 修改 `frontend/src/hooks/useSession.ts`
- 优先从 `useSearchParams()` 读取 `session_id`，fallback 到 localStorage

### T2.4 前端：Gap 页面 mount 时恢复最近 run
- [x] 修改 `frontend/src/app/gap/page.tsx`
- sessionId 就绪后查询最近 run，根据状态恢复结果或 SSE
- [x] 新增 "New Run" 按钮

### T2.5 前端：useGapStream 支持从已有结果初始化
- [x] 新增 `loadResult(data)` 方法

### T2.6 验证 Step 2
- [x] 从 Sessions 页面点击进入 Gap → URL 带 `?session_id=xxx`
- [x] 该 session 有已完成 run → 页面自动展示结果（papers、matrix、gaps）
- [x] 该 session 有运行中 run → 页面自动恢复 SSE 进度条
- [x] 页面切走再回来 → 结果仍在
- [x] 直接访问 `/gap`（无参数）→ 显示输入界面，提交 topic 时才创建 session
- [x] 在已有结果页面点击 "New Run" → 可以发起新 run

---

## Step 3 — 统一工作区语义

### T3.1 后端：Chat 历史消息查询端点
- [x] 在 `src/maelstrom/api/chat.py` 新增 `GET /api/chat/messages?session_id=xxx`
- 调用 `chat_repo.list_messages_by_session(db, session_id)`
- 返回 `list[{id, role, content, citations_json, created_at}]`

### T3.2 前端：Chat 页面加载历史消息
- [x] 修改 `frontend/src/components/chat/ChatWindow.tsx`
- mount 时调用 `GET /api/chat/messages?session_id=xxx`
- 将历史消息填充到 `messages` state 中（在用户开始新对话之前展示）
- 已有历史时滚动到底部

### T3.3 前端：侧边栏展示当前 session
- [x] 修改 `frontend/src/components/layout/Sidebar.tsx`
- Sidebar 从 URL `?session_id=` 或 localStorage 读取当前 session
- 底部展示当前 session title（调用 `GET /api/sessions/{id}` 获取）
- 点击 session 名称跳转到 `/sessions`

### T3.4 可选：路由迁移到 `/sessions/[id]/gap`
- [x] 评估是否需要将路由从 query param 迁移到路径段
  - 评估结论：暂不迁移。当前 `?session_id=` 模式已在所有页面统一使用，迁移涉及 Sidebar、所有页面 session 读取、跨页面跳转等大量改动，收益仅为 URL 可读性提升，风险收益比不合理。待有明确产品需求再推进。
- [ ] 如果迁移：创建 `frontend/src/app/sessions/[id]/gap/page.tsx` 等（暂不执行）

### T3.5 验证 Step 3
- [x] Chat 页面进入时自动展示历史消息
- [x] 侧边栏显示当前 session 名称
- [x] 从 Sessions 页面切换不同 session → Gap 和 Chat 都切换到对应上下文

---

## 依赖关系

```
T1.1 ← T1.2, T1.3          (touch_session 先实现，repo 才能调用)
T1.4, T1.5 ← T1.6          (聚合查询先实现，API 才能返回摘要)
T1.6 ← T1.7                (API 就绪后前端才能渲染)
T1.* ← T2.*                (Step 1 全部完成后再做 Step 2)
T2.1 ← T2.2                (repo 方法先实现，API 才能调用)
T2.3 ← T2.4                (useSession 改造后 Gap 页面才能拿到正确 session_id)
T2.* ← T3.*                (Step 2 全部完成后再做 Step 3)
```

## BugFix — 页面打开即创建空 Session

### BF.1 前端：useSession 改为懒创建模式
- [x] 修改 `frontend/src/hooks/useSession.ts`
- mount 时只尝试恢复已有 session（URL param → localStorage），不自动创建
- 新增 `ensureSession(title?)` 方法，仅在用户操作时调用
- sessionId 初始为 null，直到用户提交 prompt 或上传文件时才创建

### BF.2 前端：Gap 页面适配懒创建
- [x] 修改 `frontend/src/app/gap/page.tsx`
- `handleSubmit` 中调用 `ensureSession(topic)` 获取 sid
- restore 逻辑在 sessionId 为 null 时跳过

### BF.3 前端：Chat 页面及子组件适配懒创建
- [x] 修改 `frontend/src/app/chat/page.tsx` — 传递 ensureSession 给子组件
- [x] 修改 `ChatWindow.tsx` — handleSend 中调用 `ensureSession(q)`
- [x] 修改 `DocUploader.tsx` — uploadFile 中调用 `ensureSession()`

### BF.4 前端：useRouter 适配 nullable sessionId
- [x] 修改 `frontend/src/hooks/useRouter.ts`
- sessionId 参数改为 `string | null`
- `sendInput` 新增 `overrideSessionId` 参数

---

## 优先级建议

| 优先级 | 任务 | 理由 |
|--------|------|------|
| P0 | T1.1 ~ T1.6 | 后端基础设施，所有前端功能的前提 |
| P0 | T1.7 | Sessions 页面是用户感知 session 的唯一入口 |
| P1 | T2.1 ~ T2.4 | 解决"页面切走数据丢失"的核心痛点 |
| P2 | T2.5 | 体验优化，非阻塞 |
| P2 | T3.1 ~ T3.3 | 工作区语义完善 |
| P3 | T3.4 | 路由迁移，可选 |
