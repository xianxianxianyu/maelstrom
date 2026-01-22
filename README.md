# PDF to Markdown Translator

A full-stack system that converts uploaded PDFs to translated Markdown with extracted images, maintaining original document structure.

## Features

- **Multi-provider support**: ZhipuAI (GLM), OpenAI, DeepSeek
- **Secure API Key management**: Keys stored in memory only, never written to files
- **PDF text extraction** with document structure preservation
- **Image extraction** and embedding in markdown
- **Clean UI** with Tailwind CSS

## Tech Stack

- **Frontend**: Next.js 14 + TypeScript + Tailwind CSS
- **Backend**: Python + FastAPI + Pydantic
- **PDF Processing**: PyMuPDF (fitz)

## Project Structure

```
├── frontend/                 # Next.js App
│   ├── src/
│   │   ├── app/             # Pages
│   │   ├── components/      # React components
│   │   ├── lib/             # API client & storage
│   │   └── types/           # TypeScript types
│   └── package.json
│
├── backend/                  # FastAPI Application
│   ├── app/
│   │   ├── api/routes/      # API endpoints
│   │   ├── core/            # Config & key management
│   │   ├── models/          # Pydantic schemas
│   │   └── services/        # Business logic
│   │       └── providers/   # LLM providers
│   └── requirements.txt
│
└── README.md
```

## Quick Start

### 1. Backend Setup

```bash
cd backend

# Create virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the backend server
python -m app.main
```

The backend will run on `http://127.0.0.1:8000`

### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

The frontend will run on `http://localhost:3000`

## Usage

1. Open `http://localhost:3000` in your browser
2. Click the settings icon (gear) in the top right corner
3. Select a provider (DeepSeek, ZhipuAI, or OpenAI)
4. Enter your API key and click Save
5. Click "Import PDF Document" and select a PDF file
6. Wait for processing and view the translated markdown

## Available Models

| Provider | Models | Description |
|----------|--------|-------------|
| DeepSeek | deepseek-chat, deepseek-reasoner | Recommended for translation |
| ZhipuAI | glm-4, glm-4-flash, glm-4v | Chinese language support |
| OpenAI | gpt-4o, gpt-4o-mini | General purpose |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/pdf/upload` | POST | Upload and translate PDF |
| `/api/models/` | GET | Get available models |
| `/api/keys/set` | POST | Set API key (memory only) |
| `/api/keys/status` | GET | Check which providers have keys |
| `/api/keys/{provider}` | DELETE | Remove API key |

## Security

- **No .env file**: API keys are not stored in any files
- **Memory-only storage**: Keys exist only in server memory, cleared on restart
- **sessionStorage**: Frontend stores keys in sessionStorage, cleared on browser close

## License

MIT

---

# PDF 转 Markdown 翻译器

一个全栈系统，将上传的 PDF 转换为翻译后的 Markdown，提取图片并保持原始文档结构。

## 功能特点

- **多服务商支持**：智谱 AI (GLM)、OpenAI、DeepSeek
- **安全的 API Key 管理**：密钥仅存储在内存中，不写入任何文件
- **PDF 文本提取**：保持文档结构
- **图片提取**：嵌入到 Markdown 中
- **简洁的 UI**：使用 Tailwind CSS

## 技术栈

- **前端**：Next.js 14 + TypeScript + Tailwind CSS
- **后端**：Python + FastAPI + Pydantic
- **PDF 处理**：PyMuPDF (fitz)

## 项目结构

```
├── frontend/                 # Next.js 应用
│   ├── src/
│   │   ├── app/             # 页面
│   │   ├── components/      # React 组件
│   │   ├── lib/             # API 客户端和存储
│   │   └── types/           # TypeScript 类型
│   └── package.json
│
├── backend/                  # FastAPI 应用
│   ├── app/
│   │   ├── api/routes/      # API 端点
│   │   ├── core/            # 配置和密钥管理
│   │   ├── models/          # Pydantic 模型
│   │   └── services/        # 业务逻辑
│   │       └── providers/   # LLM 服务商
│   └── requirements.txt
│
└── README.md
```

## 快速开始

### 1. 后端设置

```bash
cd backend

# 创建虚拟环境（可选但推荐）
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 启动后端服务
python -m app.main
```

后端运行在 `http://127.0.0.1:8000`

### 2. 前端设置

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端运行在 `http://localhost:3000`

## 使用方法

1. 在浏览器中打开 `http://localhost:3000`
2. 点击右上角的设置图标（齿轮）
3. 选择服务商（DeepSeek、智谱 AI 或 OpenAI）
4. 输入你的 API Key 并点击保存
5. 点击"Import PDF Document"选择 PDF 文件
6. 等待处理完成，查看翻译后的 Markdown

## 可用模型

| 服务商 | 模型 | 说明 |
|--------|------|------|
| DeepSeek | deepseek-chat, deepseek-reasoner | 推荐用于翻译 |
| 智谱 AI | glm-4, glm-4-flash, glm-4v | 中文支持好 |
| OpenAI | gpt-4o, gpt-4o-mini | 通用 |

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/pdf/upload` | POST | 上传并翻译 PDF |
| `/api/models/` | GET | 获取可用模型 |
| `/api/keys/set` | POST | 设置 API Key（仅内存） |
| `/api/keys/status` | GET | 查看哪些服务商有 Key |
| `/api/keys/{provider}` | DELETE | 删除 API Key |

## 安全性

- **无 .env 文件**：API Key 不存储在任何文件中
- **仅内存存储**：Key 仅存在于服务器内存，重启即清除
- **sessionStorage**：前端将 Key 存储在 sessionStorage，关闭浏览器即清除

## 许可证

MIT
