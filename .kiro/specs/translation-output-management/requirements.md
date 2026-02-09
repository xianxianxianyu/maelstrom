# 翻译输出管理 — 需求规格说明书 (PRD)

## 1. 概述

### 1.1 背景

当前翻译结果以扁平文件形式存储在 `Translation/` 目录下：
- `{stem}.md` — 翻译后的 markdown
- `{stem}_ocr.md` — OCR 原始 markdown
- `{stem}_prompt.json` — 生成的 prompt 配置

存在以下问题：
1. **图片以 base64 内嵌** — markdown 文件体积巨大，编辑器/渲染器加载缓慢，部分查看器无法正确显示
2. **文件名冲突** — 同名 PDF 重复翻译会直接覆盖旧结果
3. **无历史记录** — 用户无法查看/回溯之前的翻译结果
4. **无结构化管理** — 所有文件平铺在同一目录，难以管理

### 1.2 目标

将翻译输出改为文件夹结构，每次翻译生成独立目录，图片提取为实际文件，并在前端提供历史记录列表。

---

## 2. EARS 需求

> 格式：`[ID] [类型] 需求描述`
> 类型：U = Ubiquitous（始终成立）, E = Event-driven, S = State-driven, O = Optional, C = Complex

### 2.1 存储结构

**REQ-S01** [U] 系统应将每次翻译结果存储在 `Translation/{id}/` 独立文件夹中，其中 `{id}` 为 8 位短 UUID（取 `uuid4().hex[:8]`）。

**REQ-S02** [U] 每个翻译文件夹内应包含以下文件：
- `translated.md` — 翻译后的双语 markdown
- `images/` — 子文件夹，存放从 markdown 中提取的图片文件
- `ocr_raw.md` — （仅 OCR 模式）OCR 原始 markdown
- `meta.json` — 元数据文件，包含：`filename`（原始 PDF 文件名）、`created_at`（ISO 时间戳）、`provider`、`model`、`enable_ocr`、`prompt_profile`（domain + terminology_count）

**REQ-S03** [U] `translated.md` 和 `ocr_raw.md` 中的图片引用应使用相对路径 `./images/{filename}` 而非 base64 data URI。

### 2.2 图片提取

**REQ-I01** [E] 当翻译管线生成包含 base64 图片的 markdown 时，系统应：
1. 扫描 markdown 中所有 `data:image/{ext};base64,{data}` 模式
2. 将每个 base64 解码为二进制文件，保存到 `images/` 子文件夹
3. 文件命名为 `fig_{序号}.{ext}`（序号从 1 开始）
4. 将 markdown 中的 data URI 替换为 `./images/fig_{序号}.{ext}`

**REQ-I02** [E] 当 OCR 管线（MineRU）返回的结果已包含实际图片文件（`OCRResult.images` 字典）时，系统应直接将图片文件写入 `images/` 子文件夹，无需 base64 编解码。

### 2.3 索引管理

**REQ-X01** [U] `Translation/index.json` 应维护所有翻译记录的索引，结构为：
```json
{
  "entries": [
    {
      "id": "a1b2c3d4",
      "filename": "paper.pdf",
      "display_name": "paper",
      "created_at": "2026-02-09T14:30:00",
      "provider": "deepseek",
      "model": "deepseek-chat",
      "enable_ocr": true
    }
  ]
}
```

**REQ-X02** [E] 当新翻译完成时，系统应将新条目追加到 `index.json` 的 `entries` 数组头部（最新在前）。

**REQ-X03** [U] 若 `index.json` 不存在，系统应自动创建并初始化为 `{"entries": []}`。

### 2.4 重名处理

**REQ-D01** [E] 当用户上传的 PDF 文件名（stem）与 `index.json` 中已有条目的 `display_name` 重复时，系统应自动添加数字后缀：
- 第 1 次：`paper`
- 第 2 次：`paper-2`
- 第 3 次：`paper-3`
- 以此类推

**REQ-D02** [U] `display_name` 仅用于前端展示和人类可读性，不影响文件夹 ID 的唯一性。

### 2.5 前端历史列表

**REQ-H01** [E] 当前端应用加载时，系统应从后端 API 获取翻译历史列表并在侧边栏展示。

**REQ-H02** [U] 历史列表应显示每条记录的：`display_name`、翻译时间（相对时间，如"2小时前"）、使用的模型。

**REQ-H03** [E] 当用户点击历史列表中的某条记录时，系统应加载该翻译的 `translated.md` 内容到主文档区域显示。若该翻译有 `ocr_raw.md`，同时加载并启用 "双语翻译/OCR 原文" 切换标签。

**REQ-H04** [E] 当新翻译完成后，历史列表应自动刷新，新条目出现在列表顶部。

**REQ-H05** [O] 用户可以从历史列表中删除某条翻译记录（删除文件夹 + 从 index.json 移除）。

### 2.6 后端 API

**REQ-A01** [U] 后端应提供以下新 API 端点：

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/translations` | GET | 返回 index.json 中的翻译列表 |
| `/api/translations/{id}` | GET | 返回指定翻译的 markdown 内容 + 元数据 |
| `/api/translations/{id}` | DELETE | 删除指定翻译（文件夹 + 索引条目） |
| `/api/translations/{id}/images/{filename}` | GET | 返回指定翻译中的图片文件（供 markdown 渲染） |

**REQ-A02** [S] 当前端请求 markdown 内容中包含 `./images/` 相对路径时，前端 markdown 渲染器应将图片路径重写为 `/api/translations/{id}/images/{filename}` 绝对 URL，以便正确加载图片。

### 2.7 向后兼容

**REQ-B01** [O] 系统可提供一次性迁移脚本，将 `Translation/` 下已有的扁平文件迁移到新的文件夹结构中。（低优先级，可后续实现）

---

## 3. 可行性分析

### 3.1 技术可行性

| 方面 | 评估 | 说明 |
|------|------|------|
| 文件夹创建 | ✅ 简单 | Python `pathlib` + `aiofiles`，已有类似逻辑 |
| Base64 提取 | ✅ 简单 | 正则匹配 `data:image/...;base64,...`，标准库 `base64.b64decode` |
| OCR 图片直写 | ✅ 简单 | `OCRResult.images` 已是 `Dict[str, bytes]`，直接写文件 |
| index.json 并发安全 | ⚠️ 中等 | 单进程 FastAPI 下用 `asyncio.Lock` 即可；多 worker 需文件锁 |
| 前端图片路径重写 | ✅ 简单 | 在 `MarkdownViewer` 渲染前做字符串替换 |
| 前端历史列表 | ✅ 简单 | 新增 Sidebar tab 或在现有 Sidebar 中添加列表组件 |
| 图片静态服务 | ✅ 简单 | FastAPI `FileResponse` 或 `StaticFiles` mount |

### 3.2 影响范围

| 文件 | 变更类型 | 影响程度 |
|------|----------|----------|
| `backend/app/api/routes/pdf.py` | 修改保存逻辑 | 高 — 核心变更点 |
| `backend/app/services/ocr_service.py` | 修改图片处理 | 中 — 不再 base64 内嵌，改为返回原始图片 |
| `backend/app/services/markdown_builder.py` | 修改图片输出 | 中 — 图片改为相对路径 |
| `backend/app/api/routes/translations.py` | 新增 | 高 — 新 API 路由 |
| `backend/app/services/translation_store.py` | 新增 | 高 — 存储管理服务 |
| `frontend/src/lib/api.ts` | 新增 API 调用 | 低 |
| `frontend/src/components/Sidebar.tsx` | 添加历史列表 | 中 |
| `frontend/src/components/MarkdownViewer.tsx` | 图片路径重写 | 低 |
| `frontend/src/app/page.tsx` | 加载历史翻译 | 中 |

### 3.3 风险与缓解

| 风险 | 概率 | 缓解措施 |
|------|------|----------|
| index.json 写入竞争 | 低（单进程） | 使用 `asyncio.Lock` 保护读写 |
| 磁盘空间增长 | 中 | 图片文件比 base64 小 ~25%；可后续加清理功能 |
| 旧翻译不兼容 | 低 | REQ-B01 迁移脚本可选实现 |
| 图片路径在不同环境下失效 | 低 | 统一使用 API 端点提供图片，不依赖文件系统路径 |

---

## 4. 数据流

```
PDF 上传
  │
  ├─ LLM 管线 → MarkdownBuilder → markdown (图片用相对路径)
  │                                  │
  │                                  ├─ 图片 bytes → Translation/{id}/images/fig_N.ext
  │                                  └─ markdown   → Translation/{id}/translated.md
  │
  └─ OCR 管线 → OCRService → OCRResult {markdown, images}
                                │
                                ├─ images dict → Translation/{id}/images/ (直接写文件)
                                ├─ 替换路径后的 ocr markdown → Translation/{id}/ocr_raw.md
                                └─ 翻译后 markdown → Translation/{id}/translated.md
  │
  └─ 更新 Translation/index.json
  └─ 返回 {id, markdown, ocr_markdown} 给前端
```

---

## 5. 优先级排序

| 优先级 | 需求 | 说明 |
|--------|------|------|
| P0 | REQ-S01~S03, REQ-I01~I02, REQ-X01~X03 | 核心存储结构 |
| P0 | REQ-A01, REQ-A02 | API 端点 |
| P1 | REQ-H01~H04, REQ-D01~D02 | 前端历史列表 + 重名处理 |
| P2 | REQ-H05 | 删除功能 |
| P3 | REQ-B01 | 旧数据迁移 |
