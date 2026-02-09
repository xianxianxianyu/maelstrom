# PDF to Markdown Translator

一个全栈 PDF 翻译系统，将英文 PDF 文档翻译为中英双语 Markdown，自动提取图片、表格和公式，保持原始文档结构。

## 功能特点

- **双管线处理**：纯 LLM 管线（PyMuPDF 解析）和 OCR + 翻译管线（PaddleOCR / MineRU），可按需切换
- **智能 Prompt 生成**：自动分析论文摘要，识别领域和术语，生成定制化翻译指令
- **多 LLM 服务商**：ZhipuAI (GLM)、OpenAI、DeepSeek，通过 Profile + Binding 灵活配置
- **多 OCR 服务商**：PaddleOCR、MineRU，支持同步/异步模式
- **翻译历史管理**：自动保存翻译结果到 `Translation/` 目录，支持查看、删除
- **异步任务管理**：支持任务取消、进度跟踪、并发控制（Semaphore=5）
- **Agent 系统**：可扩展的 Agent 框架，内置 QA Agent
- **安全的 API Key 管理**：密钥仅存储在服务器内存中，重启即清除
- **文档结构保持**：自动检测页眉页脚、推断标题层级、图文交织排版
- **后处理清洗**：自动去除代码围栏、HTML 转 Markdown、规范化空白

## 技术栈

- **前端**：Next.js 14 + TypeScript + React 18 + Tailwind CSS + React Markdown
- **后端**：Python + FastAPI + Pydantic + uvicorn
- **PDF 解析**：PyMuPDF (fitz) + pdfplumber
- **OCR**：PaddleOCR / MineRU（可选）
- **LLM SDK**：openai、zhipuai、httpx

## 项目结构

```
├── frontend/                 # Next.js 前端
│   ├── src/
│   │   ├── app/             # 页面（主页 + 布局）
│   │   ├── components/      # React 组件
│   │   │   ├── UploadButton     # PDF 上传
│   │   │   ├── MarkdownViewer   # Markdown 渲染
│   │   │   ├── Sidebar          # 侧边栏（设置 + 历史）
│   │   │   ├── LLMConfigPanel   # LLM 配置面板
│   │   │   ├── OCRConfigPanel   # OCR 配置面板
│   │   │   ├── QAPanel          # 问答面板
│   │   │   └── HistoryList      # 翻译历史列表
│   │   ├── lib/             # API 客户端 + 浏览器存储
│   │   └── types/           # TypeScript 类型定义
│   └── package.json
│
├── backend/                  # FastAPI 后端
│   ├── app/
│   │   ├── api/routes/      # API 路由
│   │   │   ├── pdf.py           # PDF 上传（瘦路由，委托给 Orchestrator）
│   │   │   ├── agent.py         # Agent QA 问答
│   │   │   ├── llm_config.py    # LLM 配置 CRUD
│   │   │   ├── ocr_config.py    # OCR 配置 CRUD
│   │   │   ├── translations.py  # 翻译历史管理
│   │   │   ├── keys.py          # API Key 管理
│   │   │   └── models.py        # 可用模型列表
│   │   ├── core/            # 配置 + Key 存储
│   │   ├── models/          # Pydantic 数据模型
│   │   └── services/        # 业务逻辑
│   │       ├── pipelines/           # 翻译管线（Pipeline 模式）
│   │       │   ├── base.py          # BasePipeline + PipelineResult + CancellationToken
│   │       │   ├── llm_pipeline.py  # LLM 管线
│   │       │   ├── ocr_pipeline.py  # OCR + 翻译管线
│   │       │   └── orchestrator.py  # 管线编排器
│   │       ├── pdf_parser.py        # PDF 结构化解析
│   │       ├── translator.py        # 多服务商翻译服务
│   │       ├── ocr_service.py       # OCR 识别封装
│   │       ├── prompt_generator.py  # 智能 Prompt 生成
│   │       ├── markdown_builder.py  # Markdown 组装
│   │       ├── post_processor.py    # 翻译后处理
│   │       ├── text_processing.py   # Markdown 分段 + 文本块合并
│   │       ├── llm_setup.py         # LLM 运行时配置服务
│   │       ├── image_utils.py       # Base64 图片提取工具
│   │       ├── task_manager.py      # 异步任务管理
│   │       └── translation_store.py # 翻译结果持久化
│   └── requirements.txt
│
├── core/                     # 核心模块（后端 + Agent 共享）
│   ├── llm/                 # LLM Multiton 管理器
│   │   ├── manager.py           # Profile + Binding 管理
│   │   ├── config.py            # LLMConfig + FunctionKey 枚举
│   │   ├── instance.py          # LLM 实例封装
│   │   └── loader.py            # YAML 配置加载/保存
│   ├── ocr/                 # OCR 管理器
│   │   ├── manager.py           # OCR Profile + Binding 管理
│   │   ├── config.py            # OCRConfig
│   │   ├── loader.py            # YAML 配置加载/保存
│   │   └── providers/           # PaddleOCR / MineRU 实现
│   └── providers/           # LLM Provider 实现
│       ├── base.py              # BaseProvider 抽象接口
│       ├── openai_compat.py     # OpenAI 兼容 API 基类
│       ├── glm.py               # ZhipuAI GLM（同步 SDK + asyncio.to_thread）
│       ├── openai.py            # OpenAI
│       └── deepseek.py          # DeepSeek
│
├── agent/                    # Agent 框架
│   ├── base.py              # BaseAgent 抽象基类
│   ├── registry.py          # Agent 注册表
│   ├── agents/
│   │   └── qa_agent.py      # QA 问答 Agent
│   ├── tools/               # Agent 工具（扩展用）
│   └── workflows/           # Agent 工作流（扩展用）
│
├── key/                      # YAML 配置文件目录
├── Translation/              # 翻译结果存储目录（自动生成）
└── README.md
```

## 快速开始

### 1. 后端

```bash
cd backend

# 创建 conda 环境
conda create -n pdf-translator python=3.11 -y
conda activate pdf-translator

# 安装依赖
pip install -r requirements.txt

# 启动服务
python -m app.main
```

后端运行在 `http://127.0.0.1:3301`

### 2. 前端

```bash
cd frontend

npm install
npm run dev
```

前端运行在 `http://localhost:3302`

## 使用方法

1. 打开 `http://localhost:3302`
2. 点击侧边栏设置图标，选择 LLM 服务商并输入 API Key
3. （可选）配置 OCR 服务商（PaddleOCR / MineRU）
4. 点击 "Import PDF Document" 上传 PDF 文件
5. 系统自动分析论文领域、生成术语表、逐段翻译
6. 查看翻译结果，支持切换 LLM 翻译 / OCR 原文视图
7. 翻译历史自动保存，可在侧边栏查看和管理

## 处理管线

### 纯 LLM 管线（默认）

```
PDF → PyMuPDF 解析（文本+图片+表格+字体信息）
    → 提取摘要 → LLM 分析领域和术语 → 生成定制化翻译 Prompt
    → 合并小文本块 → 并发翻译（Semaphore=5）
    → 后处理清洗 → 组装 Markdown（图文交织）
```

### OCR + 翻译管线

```
PDF → OCR 识别（PaddleOCR/MineRU）→ 完整 Markdown
    → 提取摘要 → LLM 分析领域和术语 → 生成定制化翻译 Prompt
    → 分段（文本/图片/表格/公式）→ 仅翻译文本段
    → 后处理清洗 → 重组 Markdown
```

## 配置系统

项目使用 Profile + Binding 模式管理 LLM 和 OCR 配置：

- **Profile**：命名配置档案（如 `translation-deepseek`），包含 provider、model、参数等
- **Binding**：将功能键（如 `translation`、`qa`）绑定到具体 Profile
- **FunctionKey**：`translation`（翻译）、`qa`（问答）、`summarization`（摘要）、`database`

配置通过 YAML 文件持久化在 `key/` 目录，支持通过 API 或前端面板修改，也可热重载。

## 可用模型

| 服务商 | 模型 | 说明 |
|--------|------|------|
| DeepSeek | deepseek-chat, deepseek-reasoner | 推荐用于翻译 |
| ZhipuAI | glm-4, glm-4-flash, glm-4v | 中文支持好 |
| OpenAI | gpt-4o, gpt-4o-mini | 通用 |

| OCR 服务商 | 模式 | 说明 |
|------------|------|------|
| PaddleOCR | sync / async | 开源 OCR |
| MineRU | vlm / doclayout_yolo | 视觉语言模型 / 传统布局检测 |

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/pdf/upload` | POST | 上传并翻译 PDF |
| `/api/pdf/cancel/{task_id}` | POST | 取消指定任务 |
| `/api/pdf/cancel-all` | POST | 取消所有任务 |
| `/api/pdf/tasks` | GET | 列出运行中的任务 |
| `/api/models/` | GET | 获取可用模型列表 |
| `/api/keys/set` | POST | 设置 API Key（仅内存） |
| `/api/keys/status` | GET | 查看各服务商 Key 状态 |
| `/api/keys/{provider}` | DELETE | 删除 API Key |
| `/api/llm-config` | GET/POST | 读取/保存 LLM 配置 |
| `/api/llm-config/reload` | POST | 从 YAML 重新加载 LLM 配置 |
| `/api/ocr-config` | GET/POST | 读取/保存 OCR 配置 |
| `/api/ocr-config/reload` | POST | 从 YAML 重新加载 OCR 配置 |
| `/api/translations` | GET | 翻译历史列表 |
| `/api/translations/{id}` | GET/DELETE | 获取/删除翻译记录 |
| `/api/translations/{id}/images/{filename}` | GET | 获取翻译中的图片 |
| `/api/agent/qa` | POST | QA 问答 |
| `/api/agent/list` | GET | 列出可用 Agent |
| `/health` | GET | 健康检查 |

## 安全性

- API Key 仅存储在服务器内存中，不写入任何文件，重启即清除
- 前端使用 sessionStorage 存储 Key，关闭浏览器即清除
- YAML 配置文件中的 `api_key` 字段可留空，运行时从内存 KeyStore 注入

## License

MIT
