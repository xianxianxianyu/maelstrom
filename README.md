# Maelstrom

Maelstrom 是一个面向学术 PDF 的多智能体翻译工作台，当前仅保留 **Electron 桌面端** 启动方式。
它把上传、异步翻译、术语管理、质量审校、论文元数据整理、问答检索串成一条工作流，核心目标是：在尽量保持原文结构与术语一致性的前提下，产出可读、可追溯、可复查的中文 Markdown。

## 快速启动（先看这里）

### 1) 环境要求

- Node.js 18+
- Python 3.10+
- Windows/macOS/Linux 均可（仓库默认脚本在 Windows 下也可直接运行）

### 2) 安装依赖（仓库根目录执行）

```bash
npm install
npm run install:frontend
npm run install:backend
```

### 3) 启动 Electron 桌面模式

```bash
npm run desktop:dev
```

该命令会由 Electron 主进程自动拉起后端和前端，再打开桌面窗口。

- 内部后端地址：`http://127.0.0.1:3301`
- 内部前端地址：`http://127.0.0.1:3302`

### 4) 首次使用必做

1. 启动后进入应用内 **配置** 页面（对应 `/config`）
2. 在 **LLM 配置** 中至少配置一个 profile，并绑定 `translation`
3. 如需问答功能，同时绑定 `qa`
4. 如需 OCR 流程，配置 OCR profile 并绑定 `ocr`

---

## 项目能力全景

- **异步翻译任务**：上传后立即返回 `task_id`，通过 SSE 实时查看进度
- **双翻译管线**：
  - 纯 LLM 管线（PyMuPDF 解析后逐块翻译）
  - OCR+翻译管线（OCR 识别后分段翻译）
- **智能术语与提示词**：根据摘要生成领域 prompt，并维护术语表
- **质量报告**：产出评分、术语问题、格式问题、未译片段、建议
- **论文资料库**：自动提取并持久化论文元数据，支持在 UI 编辑
- **问答检索（QA）**：基于翻译结果做会话式问答，支持会话与文档范围

## 技术栈

### 前端（`frontend/`）

- Next.js 14
- React 18 + TypeScript
- Tailwind CSS
- `react-markdown` + `remark/rehype`（数学公式、GFM）

核心页面：

- `/translate`：上传、进度、结果、QA
- `/history`：历史记录与回看
- `/config`：LLM/OCR/阅读设置

### 后端（`backend/`）

- FastAPI + Uvicorn
- Pydantic v2
- PDF/OCR 处理：PyMuPDF、pdfplumber、Pillow
- LLM/OCR provider 管理：`core/llm`、`core/ocr`

### 桌面端（`electron/`）

- Electron 36
- 主进程负责拉起前后端、健康检查、窗口生命周期与子进程清理

## 当前目录结构（精简）

```text
test/
├─ README.md
├─ package.json
├─ frontend/
│  ├─ src/app/(workspace)/{translate,history,config}/page.tsx
│  ├─ src/components/
│  │  ├─ WorkspaceSidebar.tsx
│  │  ├─ TranslationProgress.tsx
│  │  ├─ HistoryList.tsx
│  │  ├─ LLMConfigPanel.tsx / OCRConfigPanel.tsx
│  │  ├─ QAPanel.tsx / TerminologyPanel.tsx / QualityReport.tsx
│  │  └─ PaperMetadataDrawer.tsx
│  └─ src/lib/api.ts
├─ backend/
│  └─ app/
│     ├─ main.py
│     ├─ api/routes/
│     │  ├─ pdf.py / sse.py / translations.py
│     │  ├─ papers.py / terminology.py / quality.py / agent.py
│     │  └─ llm_config.py / ocr_config.py / keys.py / models.py
│     └─ services/
│        ├─ pipelines/{base.py,llm_pipeline.py,ocr_pipeline.py,orchestrator.py}
│        └─ translation_store.py
├─ agent/
│  ├─ workflows/translation_workflow.py
│  ├─ agents/
│  │  ├─ orchestrator_agent.py
│  │  ├─ ocr_agent.py
│  │  ├─ terminology_agent.py
│  │  ├─ translation_agent.py
│  │  ├─ review_agent.py
│  │  ├─ index_agent.py
│  │  ├─ prompt_agent_v2.py（V0 入口）
│  │  ├─ router_agent.py（v2 路由决策）
│  │  ├─ writing_agent_v2.py（V0 写作生成）
│  │  ├─ plan_agent_v2.py（V0 计划生成）
│  │  └─ verifier_agent_v2.py（V0 验证）
│  └─ event_bus.py
│  └─ core/
│     ├─ qa_context.py（v2 上下文）
│     ├─ qa_prompts.py（v2 统一Prompt）
│     ├─ qa_llm.py（v2 统一LLM服务）
│     ├─ qa_memory.py（v2 会话记忆）
│     ├─ qa_metrics.py（v2 指标统计）
│     ├─ qa_logger.py（v2 日志系统）
│     └─ types.py（v2 核心类型）
├─ core/
│  ├─ llm/（LLM配置与管理）
│  ├─ ocr/（OCR配置与管理）
│  └─ providers/（LLM/OCR providers）
├─ key/
│  ├─ llm_config.yaml
│  └─ ocr_config.yaml
└─ Translation/
   ├─ index.json
   └─ <translation_id>/
      ├─ translated.md
      ├─ ocr_raw.md (可选)
      ├─ quality_report.json (可选)
      ├─ images/
      └─ meta.json
```

## 运行方式详解

### 仅保留：桌面模式

```bash
npm run desktop:dev
```

Electron 主进程会轮询：

- `http://127.0.0.1:3301/health`
- `http://127.0.0.1:3302`

待二者可用后再打开主窗口。

## 典型使用流程

1. 进入 `/config`，完成 LLM/OCR 配置与绑定
2. 进入 `/translate` 上传 PDF
3. 后端返回 `task_id`，前端通过 SSE 订阅进度
4. 完成后通过 `task_id` 拉取结果并渲染 Markdown
5. 在侧边/面板查看质量报告、术语、论文元数据
6. 在 `/history` 回看历史结果，点击可跳转到 `/translate?translationId=...`

## 配置模型说明（重要）

项目采用 **profiles + bindings** 模型，而不是“单个全局 key”。

### LLM

- providers：`zhipuai`、`openai`、`deepseek`
- 常见 binding：`translation`、`qa`、`summarization`

### OCR

- providers：`paddleocr`、`mineru`
- binding：`ocr`
- mode：`sync` / `async`

说明：

- `GET /api/llm-config` 不回传明文 `api_key`，只返回 `has_key`
- 前端保存配置时会对未改动 key 使用 `__KEEP__` 占位
- 如果启用 OCR 但没有有效 `ocr` 绑定，会自动回退到 LLM 管线

## 关键 API 一览

### 翻译与任务

- `POST /api/pdf/upload`：上传并创建异步任务
- `GET /api/pdf/result/{task_id}`：获取结果
- `POST /api/pdf/cancel/{task_id}`：取消任务
- `POST /api/pdf/cancel-all`：取消全部
- `GET /api/pdf/tasks`：列出活动任务

### 进度流

- `GET /api/sse/translation/{task_id}`：SSE 事件流（含 `connected` / `heartbeat` / `complete`）

### 历史与质量

- `GET /api/translations`
- `GET /api/translations/{id}`
- `DELETE /api/translations/{id}`
- `GET /api/translations/{id}/images/{filename}`
- `GET /api/translations/{id}/quality`

### 论文元数据

- `GET /api/papers`
- `GET /api/papers/{task_id}`
- `PATCH /api/papers/{task_id}/sections/{section}`
- `PATCH /api/papers/{task_id}/raw`

### QA（问答检索，V0）

- `POST /api/agent/qa`：主问答接口，支持 AI 路由决策
- `GET /api/agent/qa/health`：健康检查
- `GET /api/agent/qa/trace/{trace_id}`：请求追踪
- `GET /api/agent/qa/metrics`：请求统计（总请求、路由分布、时延等）
- `GET /api/agent/qa/logs`：日志查询
- `GET /api/agent/qa/logs/trace/{trace_id}`：特定trace的完整日志

**QA V0 架构**：
- 路由策略：`FAST_PATH`（闲聊）、`DOC_GROUNDED`（文档问答）、`MULTI_HOP`（多跳推理）
- 路由决策由 AI 自动判断
- 回答生成由 AI 基于证据或常识生成
- 支持完整的请求追踪和日志记录

### 配置与密钥

- `GET/POST /api/llm-config`
- `POST /api/llm-config/reload`
- `GET/POST /api/ocr-config`
- `POST /api/ocr-config/reload`
- `POST /api/keys/set`
- `GET /api/keys/status`

## 数据落盘与可追溯性

每次翻译会在 `Translation/` 下生成独立目录，并在 `Translation/index.json` 建立索引。

常见落盘文件：

- `translated.md`
- `ocr_raw.md`（仅 OCR 流程）
- `quality_report.json`（有审校结果时）
- `images/*`
- `meta.json`

术语表默认位于：`Translation/glossaries/*.json`。

## 故障排查

- `'electron' 不是内部或外部命令`：说明根目录依赖未安装或 devDependencies 被省略，先执行 `npm install --include=dev` 再重试
- 若仍失败：执行 `npm ls electron --depth=0`，并确认存在 `node_modules/.bin/electron.cmd`
- 桌面端未启动：确认已在项目根目录执行 `npm run desktop:dev`
- 桌面窗口未弹出：查看终端日志，确认 Electron 已探测到 3301/3302 就绪
- 上传后一直处理中：检查 `/api/sse/translation/{task_id}` 是否有事件
- OCR 未生效：确认已在 `/config` 中绑定 `ocr` profile
- QA 报错：确认 `qa` 绑定存在且 profile 对应 key 可用

## 安全提示

- `key/llm_config.yaml` 与 `key/ocr_config.yaml` 可能包含真实密钥/令牌
- 不要把真实密钥提交到远程仓库
- 建议本地使用私有配置文件，或在提交前替换为占位值

## 开发验证（可选）

```bash
# 前端检查
npm --prefix frontend run lint

# Agent 层测试（若本地环境已安装 pytest）
python -m pytest agent -q
```
