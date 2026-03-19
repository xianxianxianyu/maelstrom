# CHORE-001: 当前系统缺陷盘点与优先级分级

## 依赖
- P0-12
- P1-15
- P2-10
- P3-12

## 目的
在 P1 / P2 / P3 完成后，固定当前系统仍然存在的真实缺陷，给出优先级、涉及模块、索引文件和最小示例，作为后续修复排期的基线文档。

## 执行方法
1. 检查前端路由、Session 生命周期、Gap Engine 恢复链路、文档索引链路、Synthesis 页面和自动化测试。
2. 执行以下验证命令确认当前状态：
   - `pnpm build`
   - `pnpm exec tsc --noEmit`
   - `pnpm vitest --run`
   - `PYTHONPATH=src pytest tests/unit -q`
3. 按严重度将问题分为 P0 / P1 / P2，并固定到具体模块和文件。

## 缺陷清单

### 1. `/chat` 生产构建失败 ✅ 已修复
严重度：P0（已解决）

状态：已修复。`chat/page.tsx` 已添加 `<Suspense>` 边界包裹 `useSearchParams()`。

涉及模块：前端布局层、路由层、Session 初始化

问题描述：
- 当前版本无法完成前端生产构建。
- `pnpm build` 会在 `/chat` 页面预渲染阶段报错：`useSearchParams() should be wrapped in a suspense boundary at page "/chat"`。
- 该问题会直接阻塞可发布构建，不属于仅测试失败。

索引文件：
- `frontend/src/app/layout.tsx`
- `frontend/src/app/chat/page.tsx`
- `frontend/src/components/layout/Sidebar.tsx`
- `frontend/src/hooks/useSession.ts`

小例子：
- 在 `frontend/` 目录执行 `pnpm build`，构建过程会在生成 `/chat` 页面时失败，而不是生成可部署产物。

### 2. 从 Sessions 进入 Gap Engine 会丢失目标 Session ✅ 已修复
严重度：P0（已解决）

状态：已修复。`/gap` 不再重定向，`gap/page.tsx` 是完整页面，`useSession` 从 URL `?session_id=` 读取并保留。

涉及模块：Session 列表入口、Gap 页面入口路由

问题描述：
- `Sessions` 页面提供了 “Gap Engine” 跳转按钮，但目标页面 `/gap` 当前只是一个无条件重定向页。
- `/gap?session_id=<id>` 会立刻被重定向到 `/chat`，并且不会保留原本的 `session_id`。
- 这会导致从 Session 列表进入 Gap Engine 时，用户无法进入指定会话上下文。

索引文件：
- `frontend/src/app/sessions/page.tsx`
- `frontend/src/app/gap/page.tsx`

小例子：
- 在 `Sessions` 页面点击某个会话的 “Gap Engine”。
- 浏览器先进入 `/gap?session_id=abc`，随后变成 `/chat`。
- 原本选择的 `abc` 会话不再显式保留。

### 3. 进行中的 Gap Run 不能恢复，”运行到哪保存到哪”未真正完成 ✅ 已修复
严重度：P1（已解决）

状态：已修复。Gap/Synthesis/Planning/Experiment 四个引擎页面均已实现 restore 逻辑：completed run 恢复结果，running/pending run 重连 SSE。节点级 checkpoint 持久化（LangGraph checkpointer）仍未实现，但用户体验层面的恢复已完成。

涉及模块：Gap Engine 运行态、Gap 持久化、前端恢复逻辑

问题描述：
- 当前 Gap 运行状态主要保存在服务内存 `_run_state` 中。
- 最终结果只在整条链路执行完成后才写入 `result_json`。
- 前端恢复逻辑只恢复 `completed` 的 run，不恢复 `running` 或 `pending` 的步骤级进度。
- 这意味着用户切走页面再回来时，只能看到已完成结果，无法看到进行中的运行状态。

索引文件：
- `src/maelstrom/services/gap_service.py`
- `src/maelstrom/db/gap_run_repo.py`
- `frontend/src/app/chat/page.tsx`

小例子：
- 启动一次 Gap Engine。
- 当页面跑到 `Paper Retrieval` 或 `Deduplication` 时切换到别的页面。
- 返回后，前端不会恢复这次 run 的中间进度，只会在 run 已完成时恢复最终结果。

### 4. Session-First 流程仍被绕过，系统仍会”边操作边自动建 Session” ⚠️ 部分修复
严重度：P1（仍存在）

状态：部分修复。`useSession` 不再在 mount 时自动创建 session，但 `ensureSession()` 仍允许从 `/chat` 或 `/gap` 直接操作时懒创建 session，绕过 Sessions 页面入口。如需强制 session-first，需移除 `ensureSession` 的自动创建逻辑。

涉及模块：Session hook、Chat 发送链路、PDF 上传链路

问题描述：
- 现有逻辑仍允许用户不经过 `Sessions` 页面就直接开始工作。
- `useSession()` 保留了 `ensureSession()` 的 lazy create 语义。
- 聊天发送、上传 PDF 等操作都会在没有显式 Session 时自动创建一个 Session。
- 这与“先创建 Session，再开始运行并持续保存”的目标不一致。

索引文件：
- `frontend/src/hooks/useSession.ts`
- `frontend/src/app/chat/page.tsx`
- `frontend/src/components/chat/ChatWindow.tsx`
- `frontend/src/components/chat/DocUploader.tsx`

小例子：
- 用户首次打开 `/chat`，不经过 `Sessions`。
- 直接发送一句话或上传一个 PDF。
- 系统会自动创建一个 `Untitled Session`，而不是要求先进入会话入口。

### 5. 文档上传、分享、删除不会刷新 Session 活跃时间 ✅ 已修复
严重度：P1（已解决）

状态：已修复。`doc_service.py` 在 upload、delete、share_papers_to_qa 三个路径均调用 `touch_session`。

涉及模块：文档服务、Artifact 持久化、Session 列表排序

问题描述：
- Session 列表按 `updated_at` 倒序排序。
- 但文档上传、分享到 QA、删除文档这些动作只会写入或删除 `artifacts`，不会回写 Session 活跃时间。
- 因此只做文档相关操作的会话，在 Session 列表里看起来像“没有最近活动”。

索引文件：
- `src/maelstrom/services/doc_service.py`
- `src/maelstrom/db/artifact_repo.py`
- `src/maelstrom/db/session_repo.py`
- `src/maelstrom/api/sessions.py`

小例子：
- `Session B` 今天刚上传了 3 个 PDF。
- 打开 `Sessions` 列表时，它仍可能排在旧会话后面。
- 用户看到的“最近活跃”顺序与真实使用顺序不一致。

### 6. 前端存在用户可见乱码 ✅ 已确认不存在
严重度：P1（已解决）

状态：二次扫描确认所有前端文件均为合法 UTF-8 中文，无 `鈥?` 等乱码字符。

涉及模块：Chat 头部、设置页、Chat 错误提示、Synthesis 页面

问题描述：
- 当前前端存在多处乱码字符串，已经进入用户界面。
- 这些乱码不是日志问题，而是会直接显示在按钮、标题、状态文案或错误提示中。
- 该问题会影响可读性和专业性，尤其在错误场景下会降低可诊断性。

索引文件：
- `frontend/src/components/chat/ChatHeader.tsx`
- `frontend/src/components/settings/LLMConfigForm.tsx`
- `frontend/src/components/chat/ChatWindow.tsx`
- `frontend/src/app/synthesis/page.tsx`
- `src/maelstrom/services/gap_service.py`
- `docs/README.md`

小例子：
- Chat Header 中 active 标签可能显示为 `鈥?active`。
- Chat 发送失败时提示文本显示为乱码，而不是正常中文或英文。

### 7. 自动化验证链路与当前实现不同步 ✅ 已修复
严重度：P2（已解决）

状态：已修复。前端 6 个测试文件 32 个用例全部通过（vitest --run），后端 356 个用例全部通过（4 个 paperqa 相关 skip）。测试与当前接口一致。

涉及模块：前端测试、后端测试、Python 依赖环境

问题描述：
- 前端测试和类型检查中仍保留旧接口假设，例如旧导航、旧版 `LLMConfigForm`、缺失 `ensureSession` 参数的旧组件调用方式。
- 后端单测在当前环境中还会因为缺少 `aiosqlite`、`sse_starlette` 等依赖而无法完成收集。
- 另外，部分测试代码仍引用已经不再存在的旧 `LLMConfig` 接口。
- 该问题不一定直接导致线上功能失效，但会显著削弱回归验证能力。

索引文件：
- `frontend/src/__tests__/p0_08_skeleton.test.tsx`
- `frontend/src/__tests__/p0_09_llm_config.test.tsx`
- `frontend/src/__tests__/p0_10_chat.test.tsx`
- `frontend/src/__tests__/p0_11_doc_uploader.test.tsx`
- `tests/unit/test_p0_01_schemas.py`
- `tests/unit/test_p0_05_paperqa.py`
- `pyproject.toml`

小例子：
- 执行 `pnpm vitest --run` 时，测试仍然期待 `/gap` 导航和旧版 `Save` 按钮。
- 执行 `PYTHONPATH=src pytest tests/unit -q` 时，测试收集会因为缺少依赖和旧 schema 引用而中断。

## 验收条件
- 文档明确列出当前系统的缺陷分级，至少覆盖 P0 / P1 / P2 三档。
- 每个缺陷都包含涉及模块、索引文件和一个最小示例。
- 文档可直接作为后续修复排期、任务拆分和回归验证的输入。
