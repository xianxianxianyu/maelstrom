# P0-04: 会话管理 API

## 依赖
- P0-02（SQLite 数据库层）

## 目的
实现会话（Session）的完整 CRUD REST API，作为 Gap Engine 运行和 QA Chat 的容器，管理会话生命周期和关联数据。

## 执行方法
1. 在 `src/maelstrom/api/sessions.py` 中实现路由：
   - `POST /api/sessions` — 创建新会话（可选 title），返回 Session 对象
   - `GET /api/sessions` — 列出所有会话，按 updated_at 降序
   - `GET /api/sessions/{session_id}` — 获取会话详情（含 artifact_refs, gap_runs 计数等）
   - `DELETE /api/sessions/{session_id}` — 删除会话及关联数据
2. 在 `src/maelstrom/services/session_service.py` 中封装业务逻辑：
   - 自动生成 session_id（UUID）
   - 创建时设置 status="active", created_at/updated_at 为当前时间
   - 删除时级联清理关联的 artifacts, chat_messages, gap_runs
3. 注册路由到 FastAPI app

## 验收条件
- POST 创建会话返回 201 + 完整 Session 对象
- GET 列表返回所有会话，按时间降序
- GET 单个会话返回详情，session_id 不存在时返回 404
- DELETE 成功返回 204，关联数据被清理
- 并发创建多个会话不冲突

## Unit Test
- `test_create_session`: POST 创建会话，验证返回字段完整（id, title, status, timestamps）
- `test_create_session_with_title`: POST 带 title 参数，验证 title 正确
- `test_list_sessions`: 创建 3 个会话后 GET 列表，验证数量和排序
- `test_get_session`: 创建后 GET 单个，验证字段一致
- `test_get_session_not_found`: GET 不存在的 session_id 返回 404
- `test_delete_session`: DELETE 后 GET 返回 404
- `test_delete_cascade`: 创建会话 + 关联数据，DELETE 后关联数据不可查询
