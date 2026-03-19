# FIX-004: Session 生命周期与运行恢复策略不一致

> 实施状态：Step 1 ✅ Step 2 ✅ Step 3 ✅（路由迁移除外）

## 问题（已解决）
- ~~当前 `Gap Engine` 和 `QA Chat` 的 session 由前端 `useSession()` 自动创建和复用（localStorage），用户没有显式的"新建 session → 进入工作区 → 持续运行"的操作入口。~~
- ~~`Sessions` 页面目前只是占位页（`"Session management — coming soon."`），没有展示真实 session 列表。~~
- ~~现有 session 只在创建时写入 `sessions` 表，后续活动没有持续回写 session 的活动时间和摘要信息。~~
- ~~`Gap Engine` 的运行状态主要保存在前端内存中。页面切走后再回来，前端不会自动从后端恢复。~~
- ~~`gap_runs` 没有按 session 查询的接口。~~
- ~~`Chat` 与 `Gap` 虽然共用 `session_id`，但导航与恢复路径没有围绕 session 组织起来。~~

以上问题均已通过三步走方案解决。唯一遗留：`ensureSession()` 仍允许从 `/chat` 或 `/gap` 直接操作时懒创建 session（CHORE-001 #4）。

## 解决方案：渐进式增强（三步走）

保持现有路由结构（`/gap`、`/chat`、`/sessions`）不变，分三步逐步让 session 变得可见、可恢复、可切换。

### Step 1 — Session 可见化 ✅

目标：Sessions 页面从占位页变成真实的 session 列表，session 的活动信息持续回写。（已完成）

#### 1.1 后端：session 活动信息回写
- `gap_run_repo` 的 `create_gap_run` 和 `update_gap_run_status` 在写入/更新 gap_run 后，同步调用 `session_repo.touch_session(db, session_id)` 更新 `sessions.updated_at`
- `chat_repo` 的 `create_chat_message` 在写入消息后，同步调用 `session_repo.touch_session(db, session_id)`
- `session_repo` 新增 `touch_session(db, session_id)` 方法：仅更新 `updated_at` 为当前时间

#### 1.2 后端：session 列表聚合 API
- 改造 `GET /api/sessions`，返回每个 session 的聚合摘要：
  - `run_count`: 该 session 下 gap_runs 总数
  - `latest_run_status`: 最近一次 gap_run 的 status
  - `latest_run_topic`: 最近一次 gap_run 的 topic
  - `message_count`: 该 session 下 chat_messages 总数
- 实现方式：在 `session_repo.list_sessions_with_summary(db)` 中用 LEFT JOIN 聚合，或在 API 层分别查询后合并
- 新增 `gap_run_repo.count_by_session(db, session_id)` 和 `gap_run_repo.latest_by_session(db, session_id)`
- 新增 `chat_repo.count_by_session(db, session_id)`

#### 1.3 前端：Sessions 页面实现
- 替换占位内容，调用 `GET /api/sessions` 渲染 session 卡片列表
- 每张卡片展示：title、updated_at（相对时间）、run_count、latest_run_status、message_count
- 提供"New Session"按钮，调用 `POST /api/sessions` 创建后刷新列表
- 提供"Delete"操作（确认后调用 `DELETE /api/sessions/{id}`）
- 点击卡片上的"Gap Engine"按钮 → 跳转 `/gap?session_id=xxx`
- 点击卡片上的"QA Chat"按钮 → 跳转 `/chat?session_id=xxx`

### Step 2 — Gap 运行恢复 ✅

目标：Gap 页面进入时能从后端恢复最近 run 的状态和结果，不再依赖前端内存。（已完成，Synthesis/Planning/Experiment 也已同步实现）

#### 2.1 后端：按 session 查询 gap runs
- `gap_run_repo` 新增 `list_by_session(db, session_id, limit=10)` — 按 `created_at DESC` 返回该 session 的 run 列表
- Gap API 新增 `GET /api/gap/runs?session_id=xxx&limit=1` 端点

#### 2.2 前端：useSession 支持 URL 参数
- `useSession()` 改造：优先从 URL search params 读取 `session_id`，如果有则使用并写入 localStorage；如果没有则 fallback 到现有 localStorage 逻辑
- 这样从 Sessions 页面点击进入时使用显式 session_id，直接访问 `/gap` 时仍兼容旧行为

#### 2.3 前端：Gap 页面恢复逻辑
- Gap 页面 mount 后，在 `sessionId` 就绪时调用 `GET /api/gap/runs?session_id=xxx&limit=1`
- 如果返回的 run 状态为 `completed`：调用 `GET /api/gap/run/{run_id}/result` 加载结果，直接渲染 papers/matrix/gaps/candidates
- 如果返回的 run 状态为 `running`：调用 `start(run_id)` 重新连接 SSE 恢复进度
- 如果返回的 run 状态为 `pending`：同 running 处理
- 如果没有 run 或最近 run 为 `failed`：显示空白输入界面（现有行为）
- 新增"New Run"按钮，允许在已有结果的情况下发起新 run

### Step 3 — 统一工作区语义 ✅

目标：侧边栏感知当前 session，Chat 页面也支持 session 恢复，session 成为完整的研究上下文容器。（已完成，路由迁移评估完成但暂不执行）

#### 3.1 前端：侧边栏 session 感知
- Sidebar 底部展示当前 session title（从 context 或 URL 读取）
- 可选：侧边栏展示最近 3 个 session 的快速切换入口

#### 3.2 前端：Chat 页面 session 恢复
- Chat 页面进入时，如果 URL 带 `session_id`，自动加载该 session 的历史消息（`GET /api/chat/messages?session_id=xxx`）
- 自动加载该 session 已索引的文档列表

#### 3.3 可选：路由迁移
- 将路由从 `/gap?session_id=xxx` 迁移到 `/sessions/[id]/gap`
- 此步骤为可选，视产品需求决定是否执行

## 涉及文件

### Step 1
| 文件 | 改动 |
|------|------|
| `src/maelstrom/db/session_repo.py` | 新增 `touch_session()`、`list_sessions_with_summary()` |
| `src/maelstrom/db/gap_run_repo.py` | 新增 `count_by_session()`、`latest_by_session()`；`create_gap_run` 和 `update_gap_run_status` 中触发 touch |
| `src/maelstrom/db/chat_repo.py` | `create_chat_message` 中触发 touch；新增 `count_by_session()` |
| `src/maelstrom/api/sessions.py` | `list_sessions` 返回聚合摘要 |
| `src/maelstrom/api/session_models.py` | `SessionResponse` 新增聚合字段 |
| `frontend/src/app/sessions/page.tsx` | 完整重写为 session 列表页 |

### Step 2
| 文件 | 改动 |
|------|------|
| `src/maelstrom/db/gap_run_repo.py` | 新增 `list_by_session()` |
| `src/maelstrom/api/gap.py` | 新增 `GET /api/gap/runs` 端点 |
| `frontend/src/hooks/useSession.ts` | 支持从 URL search params 读取 session_id |
| `frontend/src/app/gap/page.tsx` | mount 时查询最近 run 并恢复 |
| `frontend/src/hooks/useGapStream.ts` | 可能需要支持从已有结果初始化 state |

### Step 3
| 文件 | 改动 |
|------|------|
| `frontend/src/components/layout/Sidebar.tsx` | 展示当前 session 信息 |
| `frontend/src/app/chat/page.tsx` | 支持 session 恢复 |
| `src/maelstrom/api/chat.py` | 可能需要 `GET /api/chat/messages` 端点 |

## 验收条件

### Step 1
- Sessions 页面展示真实 session 列表，按 `updated_at` 降序排列
- 每个 session 卡片显示 run 数量、最近 run 状态、消息数量
- 创建 gap run 后，对应 session 的 `updated_at` 被更新
- 发送 chat message 后，对应 session 的 `updated_at` 被更新
- 可以从 Sessions 页面创建新 session、删除 session
- 点击 session 卡片可跳转到 `/gap?session_id=xxx` 或 `/chat?session_id=xxx`

### Step 2
- 从 Sessions 页面点击进入 Gap 页面，URL 携带 `session_id`
- 如果该 session 有已完成的 run，页面自动加载并展示结果
- 如果该 session 有运行中的 run，页面自动恢复 SSE 进度
- 页面切走再回来，结果不丢失
- 直接访问 `/gap`（无 session_id 参数）仍兼容旧行为

### Step 3
- 侧边栏显示当前 session 名称
- Chat 页面进入时自动加载历史消息
- 切换 session 后，Gap 和 Chat 都切换到对应上下文
