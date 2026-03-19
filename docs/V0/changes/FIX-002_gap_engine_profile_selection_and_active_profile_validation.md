# FIX-002: Gap Engine 缺少模型选择且 `active_profile` 悬空导致误报未配置

## 依赖
- P0-03（LLM Config API）
- P0-09（LLM Config 前端）
- P1-11（Gap Engine API endpoints）
- P1-13（Gap Engine 前端页面）

## 目的
修复“Settings 中某个 profile 已配置且连通，但 Gap Engine 仍报 `LLM not configured (no API key)`”的问题，并让 Gap Engine 支持在每次运行前显式选择使用哪个模型 profile。

## 问题现象
- 用户在 Settings 中新增或编辑 profile，例如 `ds`
- `Test Connection` 对该 profile 返回成功
- Gap Engine 页面发起 `POST /api/gap/run` 时仍返回 `400`
- 返回文案为 `LLM not configured (no API key)`
- 当前 UI 无法在 Gap Engine 页面选择“本次运行使用哪个模型”

## 根因
1. Gap Engine 当前只读取全局 `active_profile`
   - `src/maelstrom/api/gap.py` 在启动 run 前调用 `cfg.get_active_profile()`，并检查 `profile.api_key`
   - `POST /api/gap/run` 当前不接收 `profile_slug` 或其他模型选择参数
2. Settings 页的连接测试与 Gap Engine 使用的配置来源不一致
   - `frontend/src/components/settings/LLMConfigForm.tsx` 的 `Test Connection` 使用当前 `selectedSlug`
   - `src/maelstrom/api/config.py` 的 `/api/config/test/llm` 优先按请求中的 `slug` 测试
   - 因此“选中的 profile 可用”并不等于“当前 active profile 可用”
3. 配置保存缺少 `active_profile` 有效性约束
   - `MaelstromConfig.active_profile` 默认值为 `"default"`
   - 若配置文件中只存在 `profiles.ds`，但 `active_profile` 仍是 `"default"`，则 `get_active_profile()` 返回空
   - `update_config()` 当前不会拒绝这种悬空配置
4. 错误文案过于笼统
   - `Gap Engine` 将“active profile 不存在”和“active profile 存在但 api_key 为空”统一报成 `LLM not configured (no API key)`
   - 用户无法直接判断是配置未保存、active profile 错误，还是 key 为空

## 执行方法
1. 为 Gap Engine 增加按次选择 profile 的能力
   - Gap 页面加载时调用 `GET /api/config`
   - 展示可用 profile 列表，并提供 `Profile / Model` 选择控件
   - 用户提交 run 时，前端向 `POST /api/gap/run` 传入 `{ topic, session_id, profile_slug }`
   - 若用户未显式选择，则默认使用当前有效的 `active_profile`
2. 扩展 Gap API
   - `src/maelstrom/api/gap.py` 接收可选字段 `profile_slug`
   - 若传入 `profile_slug`，优先按该 slug 查找 profile
   - 若未传入，则回退到 `active_profile`
   - 若目标 profile 不存在，返回 `400 Profile not found`
   - 若目标 profile 存在但 `api_key` 为空，返回 `400 Selected profile has no api_key`
3. 调整 Gap Engine 执行上下文
   - `gap_service.start_run()` 与 `_execute_run()` 接收 `profile_slug` 或已解析的 profile
   - 工作流 state 中的 `llm_config` 不再隐式依赖全局 active profile，而是使用本次运行选定的 profile
   - 这样一次运行的模型来源是显式且可追踪的
4. 修复 Settings 配置一致性
   - `update_config()` 保存前校验 `active_profile in profiles`
   - 若 `profiles` 非空且 `active_profile` 无效，则拒绝保存并返回 400，或归一化为第一个有效 profile
   - 新增第一个 profile 时，自动设为 `active_profile`
   - 删除非 active profile 后，仍需保证 `active_profile` 不悬空
5. 统一前端展示逻辑
   - Settings 页面应显式标识 active profile
   - 当当前 active profile 无效时，页面要展示配置异常提示，而不是仅把下拉选项回退到第一个 profile
   - Gap 页面所见的 profile 列表与 Settings 页保持一致
6. 改进错误提示
   - 不再使用单一的 `LLM not configured (no API key)` 覆盖全部异常
   - 至少区分以下场景：
     - `Active profile 'default' not found`
     - `Selected profile 'ds' has no api_key`
     - `No profile configured`

## API 变更
| 方法 | 路径 | 变更 |
|------|------|------|
| `POST` | `/api/gap/run` | 请求体新增可选字段 `profile_slug` |
| `GET` | `/api/config` | 保持不变，用于前端读取 profiles 与 active_profile |
| `PUT` | `/api/config` | 增加 `active_profile` 有效性校验 |

### `POST /api/gap/run` 请求体
```json
{
  "topic": "five latest agentic topics",
  "session_id": "session-uuid",
  "profile_slug": "ds"
}
```

### `POST /api/gap/run` 解析规则
1. 若传入 `profile_slug`，使用该 profile
2. 否则使用 `active_profile`
3. 若最终未解析出合法 profile，则返回 400

## 前端变更
1. `frontend/src/app/gap/page.tsx`
   - 加载 profile 列表
   - 新增运行前 profile 选择
   - 发起 run 时传入 `profile_slug`
2. `frontend/src/components/settings/LLMConfigForm.tsx`
   - 明确展示 active profile 状态
   - 修复 `active_profile` 与 `selectedSlug` 脱节的问题
   - 保存时阻止提交无效 `active_profile`

## 后端变更
1. `src/maelstrom/api/gap.py`
   - 解析 `profile_slug`
   - 提供更准确的错误文案
2. `src/maelstrom/services/gap_service.py`
   - 接收并使用本次运行选定的 profile
3. `src/maelstrom/services/llm_config_service.py`
   - 增加 `active_profile` 校验/归一化逻辑
4. `src/maelstrom/schemas/llm_config.py`
   - 如需更严格校验，可在 schema 层增加合法性检查

## 不采用方案
- 继续仅依赖全局 `active_profile`
  - 缺点：Gap Engine 无法按次切换模型
  - 缺点：Settings 测试通过与 Gap 可运行之间仍可能不一致
- 当 `active_profile` 无效时静默回退到第一个 profile
  - 缺点：行为不透明，用户无法知道实际运行用了哪个模型
  - 缺点：不利于复现与调试
- 将 embedding key 当作 Gap Engine 的 LLM key 兜底
  - 缺点：语义错误，embedding 与 generation 配置职责不同

## 涉及文件
| 文件 | 操作 |
|------|------|
| `frontend/src/app/gap/page.tsx` | 新增 profile 选择与请求参数 |
| `frontend/src/components/settings/LLMConfigForm.tsx` | 修复 active profile 显示与保存逻辑 |
| `src/maelstrom/api/gap.py` | 支持 `profile_slug`，细化错误返回 |
| `src/maelstrom/services/gap_service.py` | 使用本次 run 的 profile 执行工作流 |
| `src/maelstrom/services/llm_config_service.py` | 校验或归一化 `active_profile` |
| `src/maelstrom/schemas/llm_config.py` | 视实现方式补充配置约束 |

## 验收条件
- Settings 中存在多个 profile 时，Gap Engine 页面可显式选择本次运行使用的 profile
- `POST /api/gap/run` 可接受并正确解析 `profile_slug`
- 当 `profile_slug=ds` 且 `ds.api_key` 存在时，即使 `active_profile` 为其他值，Gap run 仍可成功启动
- 当 `active_profile` 悬空时，Settings 保存会被阻止或自动归一化，不再写入无效配置
- Gap Engine 的错误文案可区分“profile 不存在”和“api_key 为空”
- Settings 的 LLM 测试结果与 Gap Engine 实际使用的 profile 语义一致，不再误导用户

## Unit Test
- `test_gap_run_uses_explicit_profile_slug`
- `test_gap_run_falls_back_to_active_profile`
- `test_gap_run_returns_400_when_profile_slug_missing`
- `test_gap_run_returns_400_when_selected_profile_has_no_key`
- `test_update_config_rejects_invalid_active_profile`
- `test_gap_page_sends_selected_profile_slug`
- `test_settings_save_blocks_or_repairs_invalid_active_profile`
