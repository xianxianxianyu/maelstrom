# P0-02: SQLite 数据库层

## 依赖
- P0-01（Pydantic Schema）

## 目的
实现基于 aiosqlite 的异步数据库层，提供会话、Artifact、聊天消息、Gap 运行记录的 CRUD 操作，使用 WAL 模式支持并发读写。

## 执行方法
1. 在 `src/maelstrom/db/` 下创建：
   - `database.py` — 数据库连接管理（单例 async 连接池，WAL 模式启用）
   - `migrations.py` — 表创建 DDL（sessions, artifacts, chat_messages, gap_runs）
   - `session_repo.py` — Session CRUD（create, get_by_id, list_all, delete, update）
   - `artifact_repo.py` — Artifact CRUD（create, get_by_id, list_by_session, list_by_type）
   - `chat_repo.py` — ChatMessage CRUD（create, list_by_session）
   - `gap_run_repo.py` — GapRun CRUD（create, get_by_id, update_status, update_result）
   - `run_paper_repo.py` — RunPaper 批量写入（bulk_create_for_run）、按 run_id 查询（list_by_run）
2. 表结构：
   - `sessions`: id TEXT PK, title TEXT, status TEXT, created_at TEXT, updated_at TEXT
   - `artifacts`: id TEXT PK, session_id TEXT FK, type TEXT, data_json TEXT, created_at TEXT
   - `chat_messages`: id TEXT PK, session_id TEXT FK, role TEXT, content TEXT, citations_json TEXT, created_at TEXT
   - `gap_runs`: id TEXT PK, session_id TEXT FK, topic TEXT, status TEXT, result_json TEXT, created_at TEXT, completed_at TEXT
   - `run_papers`: id TEXT PK, run_id TEXT FK, paper_json TEXT, created_at TEXT — **按 run_id 持久化检索到的完整 PaperRecord**，为前端 PaperList 和 Gap→QA 论文共享提供稳定数据源
3. 启动时自动执行 `CREATE TABLE IF NOT EXISTS`
4. 所有 repo 方法接收/返回 Pydantic model，内部做 dict ↔ row 转换

## 验收条件
- 数据库文件创建成功，WAL 模式启用（`PRAGMA journal_mode` 返回 `wal`）
- 四张表均可正常 CRUD
- 外键约束生效（删除 session 时关联数据级联删除或报错）
- 所有 repo 方法为 async

## Unit Test
- `test_database_init`: 验证数据库初始化后五张表存在（sessions, artifacts, chat_messages, gap_runs, run_papers）
- `test_wal_mode`: 验证 `PRAGMA journal_mode` 返回 `wal`
- `test_session_crud`: 创建 → 读取 → 更新 → 删除 Session，验证每步数据正确
- `test_artifact_crud`: 创建 Artifact 并按 session_id 和 type 筛选
- `test_chat_message_crud`: 创建多条消息，按 session_id 列出，验证顺序
- `test_gap_run_crud`: 创建 GapRun，更新 status 和 result，验证字段变更
- `test_cascade_delete`: 删除 session 后，关联的 artifacts/messages/runs 不可查询
- `test_concurrent_read_write`: 并发读写不死锁（WAL 模式验证）
- `test_run_paper_bulk_create`: 批量写入 50 条 RunPaper，验证 list_by_run 返回全部
- `test_run_paper_cascade_delete`: 删除 gap_run 后关联的 run_papers 不可查询
