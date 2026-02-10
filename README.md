# Maelstrom

> *A vortex that devours documents and distills structured knowledge.*

Maelstrom 是一个多 Agent 协作的全栈 PDF 翻译系统。五个专职 Agent——Orchestrator（编排）、Terminology（术语）、Translation（翻译）、Review（审校）、QA（问答）——在共享上下文中协同工作，将英文 PDF 文档翻译为结构完整保留的中英双语 Markdown，自动提取图片、表格和公式。

## 为什么叫 Maelstrom

Maelstrom（大漩涡）源自北欧传说中的巨型海洋漩涡。在这里，它象征着系统吞噬海量 PDF 文档后，通过多 Agent 流水线层层提炼——术语锚定、智能翻译、质量审校、自动修正——最终输出结构化的双语知识文档。文档进入漩涡，知识从漩涡中涌出。

## 功能特点

- **多 Agent 编排**：OrchestratorAgent 统一调度术语提取、翻译、审校、自动修正五阶段流程
- **双管线处理**：纯 LLM 管线（PyMuPDF 解析）和 OCR + 翻译管线（PaddleOCR / MineRU），TranslationAgent 根据文档特征自动选择
- **智能 Prompt 生成**：自动分析论文摘要，识别领域和术语，生成定制化翻译指令
- **质量闭环**：ReviewAgent 三维度审校（术语一致性 + 格式完整性 + 未翻译检测），评分低于 70 分自动修正重审
- **多 LLM 服务商**：ZhipuAI (GLM)、OpenAI、DeepSeek，通过 Profile + Binding 灵活配置
- **多 OCR 服务商**：PaddleOCR、MineRU，支持同步/异步模式
- **实时进度推送**：EventBus + SSE 全流程事件流，前端实时展示每个 Agent 阶段进度
- **阅读偏好定制**：字体（16 种含衬线/无衬线/等宽）、字号、行高、内容宽度实时调节
- **翻译历史管理**：自动保存翻译结果到 `Translation/` 目录，支持查看、删除
- **安全的 API Key 管理**：密钥仅存储在服务器内存中，重启即清除

## 技术栈

- **前端**：Next.js 14 + TypeScript + React 18 + Tailwind CSS + React Markdown + KaTeX
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
│   │   │   ├── MarkdownViewer   # Markdown 渲染（CSS 变量驱动阅读偏好）
│   │   │   ├── Sidebar          # 侧边栏（设置 + 历史）
│   │   │   ├── LLMConfigPanel   # LLM 配置面板
│   │   │   ├── OCRConfigPanel   # OCR 配置面板
│   │   │   ├── TranslationProgress  # SSE 实时进度
│   │   │   ├── QAPanel          # 问答面板
│   │   │   └── HistoryList      # 翻译历史列表
│   │   ├── contexts/        # React Context
│   │   │   ├── LLMConfigContext     # LLM 配置状态
│   │   │   └── ReaderSettingsContext # 阅读偏好状态
│   │   ├── lib/             # API 客户端 + 浏览器存储
│   │   └── types/           # TypeScript 类型定义
│   └── package.json
│
├── backend/                  # FastAPI 后端
│   ├── app/
│   │   ├── api/routes/      # API 路由
│   │   │   ├── pdf.py           # PDF 上传（瘦路由，委托给 Orchestrator）
│   │   │   ├── sse.py           # SSE 进度推送
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
│       ├── glm.py               # ZhipuAI GLM
│       ├── openai.py            # OpenAI
│       └── deepseek.py          # DeepSeek
│
├── agent/                    # Agent 框架
│   ├── base.py              # BaseAgent 抽象基类
│   ├── registry.py          # Agent 注册表
│   ├── context.py           # AgentContext 共享上下文
│   ├── event_bus.py         # SSE 事件总线
│   ├── models.py            # QualityReport 等数据模型
│   ├── agents/
│   │   ├── orchestrator_agent.py  # 编排 Agent（5 阶段流程）
│   │   ├── terminology_agent.py   # 术语提取 Agent
│   │   ├── translation_agent.py   # 翻译 Agent（管线选择 + 执行）
│   │   ├── review_agent.py        # 审校 Agent（质量评分）
│   │   └── qa_agent.py            # QA 问答 Agent
│   ├── tools/               # Agent 工具
│   │   └── doc_search_tool.py     # 文档搜索工具
│   └── workflows/
│       └── translation_workflow.py  # 翻译工作流入口
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
conda create -n maelstrom python=3.11 -y
conda activate maelstrom

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

## Agent 翻译系统架构

Maelstrom 的核心是多 Agent 协作架构，由 OrchestratorAgent 统一编排，各 Agent 通过共享的 `AgentContext` 传递数据。

### 整体流程

```
PDF 上传 → OrchestratorAgent 编排
  ├── Phase 1: TerminologyAgent 术语提取（前 3000 字符 → LLM 分析）
  ├── Phase 2: TranslationAgent 翻译
  │     ├── 文档特征分析（公式密度、表格数、语言分布）
  │     ├── 管线选择（LLM 直接翻译 / OCR + 翻译）
  │     ├── Prompt 生成（领域识别 + 术语注入）
  │     └── 执行翻译（带重试，最多 3 次）
  ├── Phase 3: ReviewAgent 质量审校（术语一致性 + 格式完整性 + 未翻译检测）
  ├── Phase 4: 质量 < 70 分 → 自动修正重审（最多 1 次，复用 OCR 结果）
  └── Phase 5: 保存结果到 TranslationStore
```

### AgentContext 共享上下文

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | `str` | 翻译任务唯一标识 |
| `filename` | `str` | PDF 文件名 |
| `file_content` | `bytes` | PDF 原始字节 |
| `event_bus` | `EventBus` | SSE 事件总线，推送实时进度 |
| `enable_ocr` | `bool` | 是否启用 OCR 管线 |
| `glossary` | `dict[str, str]` | 术语表 {英文: 中文} |
| `prompt_profile` | `PromptProfile` | LLM 生成的翻译配置（领域、术语、prompt） |
| `translated_md` | `str` | 翻译后的 Markdown |
| `images` | `dict[str, bytes]` | PDF 提取的图片 |
| `ocr_md` | `str` | OCR 识别的原始 Markdown |
| `ocr_images` | `dict[str, bytes]` | OCR 提取的图片 |
| `quality_report` | `QualityReport` | 审校质量报告（评分 + 问题列表） |
| `cancellation_token` | `CancellationToken` | 取消令牌 |

### 翻译管线

TranslationAgent 根据文档特征自动选择管线：

- **LLM 管线**（默认）：PyMuPDF 解析 → 文本块合并 → 并发翻译（Semaphore=5）→ 后处理 → Markdown 组装
- **OCR 管线**：PaddleOCR/MineRU 识别 → 逐段翻译 → 后处理清洗

auto_fix 场景下，TranslationAgent 检测到 `ctx` 已有 `prompt_profile` 和 `translated_md`，跳过文档分析和 Prompt 生成，直接复用已有配置重新翻译，OCR 结果也会复用。

### ReviewAgent 审校

ReviewAgent 对翻译结果进行三维度检查：

1. **术语一致性**：对照 glossary 检查术语翻译是否统一
2. **格式完整性**：检测断裂表格、未闭合公式、损坏标题、缺失图片引用
3. **未翻译检测**：识别残留的英文段落

综合评分 0–100，低于 70 分触发自动修正。

### 事件推送

全流程通过 EventBus + SSE 实时推送进度事件到前端，事件格式：

```json
{
  "agent": "orchestrator | translation | review | pipeline",
  "stage": "terminology | analysis | translating | review | complete | ...",
  "progress": 0-100,
  "detail": { "message": "人类可读的进度描述" }
}
```

前端 `TranslationProgress` 组件订阅 SSE 流，展示阶段进度条和事件日志。

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

## 安全性

- API Key 仅存储在服务器内存中，不写入任何文件，重启即清除
- 前端使用 sessionStorage 存储 Key，关闭浏览器即清除
- YAML 配置文件中的 `api_key` 字段可留空，运行时从内存 KeyStore 注入

## License

MIT
