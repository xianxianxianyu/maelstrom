# FIX-001: Gap Engine 默认 session 缺失导致 `/api/gap/run` 返回 404

## 依赖
- P0-04（Session API）
- P1-11（Gap Engine API endpoints）
- P1-13（Gap Engine 前端页面）

## 目的
修复 Gap Engine 页面首次使用时固定传入 `"default"` `session_id`，导致后端查无会话并返回 404，同时前端吞掉错误、用户无法直接理解失败原因的问题。

## 问题现象
- 打开 `/gap`，输入 topic 后，前端发起 `POST /api/gap/run`
- 后端日志显示 `POST /api/gap/run 404 Not Found`
- 当前数据库 `sessions` 为空时，页面无法启动 Gap run
- UI 无明确错误文案，用户只能从浏览器控制台或后端日志定位问题

## 根因
1. `frontend/src/app/gap/page.tsx` 将 `sessionId` 写死为 `"default"`。
2. `src/maelstrom/api/gap.py` 在启动 run 前调用 `session_repo.get_session()` 校验会话，不存在则返回 `404 Session not found`。
3. 当前前端没有在首次进入 Gap/Chat 页面时自动创建 session，也没有持久化真实 `session_id`。
4. `handleSubmit` 的 `catch` 分支仅执行 `setStarted(false)`，没有把后端 `detail` 展示给用户。

## 执行方法
1. 引入前端会话初始化逻辑
   - Gap 页与 Chat 页不再硬编码 `"default"`
   - 页面加载时优先读取本地持久化的 `session_id`
   - 若本地不存在，或后端查询该 session 返回 404，则调用 `POST /api/sessions` 创建新会话
   - 将返回的真实 `session_id` 写入前端状态与本地持久化
2. 统一会话来源
   - 抽取 `getOrCreateSession()` 或 `useSession()` 之类的共享封装，供 Gap / Chat 页面复用
   - 避免每个页面各自维护默认 session 规则
3. 修复 Gap 提交流程
   - `handleSubmit` 在调用 `POST /api/gap/run` 前确保 session 已完成初始化
   - 请求体中的 `session_id` 必须使用真实存在的会话 ID
4. 补全错误展示
   - 当 `POST /api/gap/run` 返回非 2xx 时，读取并展示后端 `detail`
   - 对 `Session not found` 提供用户可理解的提示，例如“当前会话不存在，请刷新后重试”或“正在重建会话”
5. 保持后端校验不变
   - `src/maelstrom/api/gap.py` 继续要求调用方传入合法 `session_id`
   - 不在后端隐式创建 `"default"` session，避免把会话生命周期变成隐藏行为

## 不采用方案
- 后端启动时自动插入 `"default"` session
  - 缺点：隐藏状态来源，不利于多会话管理
  - 缺点：Gap / Chat / Sessions 的会话语义不一致
  - 缺点：删除或切换会话后容易产生“幽灵默认会话”

## 涉及文件
| 文件 | 操作 |
|------|------|
| `frontend/src/app/gap/page.tsx` | 去掉硬编码 `"default"`，接入真实 `session_id`，展示启动错误 |
| `frontend/src/app/chat/page.tsx` | 与 Gap 页统一 session 初始化策略 |
| `frontend/src/lib/*` 或 `frontend/src/hooks/*` | 新增前端 session 获取/创建封装 |
| `src/maelstrom/api/gap.py` | 保持显式校验；必要时补充更清晰的错误文案 |
| `src/maelstrom/api/sessions.py` | 复用现有创建会话接口，无需改变契约 |

## 验收条件
- 数据库 `sessions` 为空时，首次进入 `/gap` 仍可成功启动 run
- `POST /api/gap/run` 请求体中的 `session_id` 为真实存在的会话 ID，而非固定 `"default"`
- 删除当前 session 或清空本地缓存后，页面可自动重建新会话
- 后端返回 4xx/5xx 时，页面可见明确错误信息，不再仅依赖日志定位
- Gap 页面与 Chat 页面使用同一套 session 初始化/持久化机制
- 不引入隐藏的后端默认 session 创建逻辑

## Unit Test
- `test_gap_page_creates_session_when_missing`
- `test_gap_page_reuses_persisted_session`
- `test_gap_page_recreates_deleted_session`
- `test_gap_submit_uses_real_session_id`
- `test_gap_error_detail_is_rendered`
- `test_chat_page_uses_shared_session_bootstrap`
