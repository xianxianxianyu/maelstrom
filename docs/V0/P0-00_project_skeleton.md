# P0-00: Python 项目骨架 + 依赖管理

## 依赖
- 无

## 目的
搭建 Maelstrom V0 后端 Python 项目的基础结构，使用 `uv` 管理依赖，建立标准化的目录布局和开发工具链，为后续所有后端 task 提供可运行的项目环境。

## 执行方法
1. 使用 `uv init` 初始化项目，生成 `pyproject.toml`
2. 配置 `pyproject.toml`：
   - Python `>=3.11, <3.13`
   - 核心依赖：fastapi, uvicorn, sse-starlette, langgraph, langgraph-checkpoint-sqlite, paper-qa, aiosqlite, httpx, pydantic, arxiv, Levenshtein
   - 开发依赖：pytest, pytest-asyncio, ruff, httpx（测试客户端）
3. 创建目录结构：
   ```
   maelstrom/
   ├── pyproject.toml
   ├── src/
   │   └── maelstrom/
   │       ├── __init__.py
   │       ├── main.py              # FastAPI app 入口
   │       ├── schemas/             # Pydantic models
   │       ├── db/                  # SQLite 数据库层
   │       ├── api/                 # API routes
   │       ├── services/            # 业务逻辑
   │       ├── adapters/            # 论文检索适配器
   │       └── graph/               # LangGraph 工作流
   ├── tests/
   │   ├── conftest.py
   │   ├── unit/
   │   └── integration/
   └── data/                        # 本地文件存储（PDF 等）
   ```
4. 配置 `ruff` lint/format 规则
5. 创建 `main.py` 最小 FastAPI app（含 health check endpoint）
6. 验证 `uv sync` 依赖安装成功

## 验收条件
- `uv sync` 无报错，所有依赖正确安装
- `python -m maelstrom.main` 或 `uvicorn maelstrom.main:app` 可启动服务
- `GET /health` 返回 `{"status": "ok"}`
- `ruff check src/` 无 lint 错误
- 目录结构完整，所有 `__init__.py` 存在

## Unit Test
- `test_health_check`: 使用 `httpx.AsyncClient` + FastAPI `TestClient` 验证 `GET /health` 返回 200 + `{"status": "ok"}`
- `test_project_structure`: 验证关键目录和文件存在（`src/maelstrom/__init__.py`, `pyproject.toml` 等）
- `test_imports`: 验证 `import maelstrom` 不报错
