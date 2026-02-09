# 翻译输出管理 — 技术设计

## 1. 新增模块

### 1.1 `backend/app/services/translation_store.py` — 存储管理服务

```python
class TranslationStore:
    """管理 Translation/ 目录下的翻译结果存储"""
    
    _lock: asyncio.Lock  # 保护 index.json 并发写入
    
    async def save(self, filename, translated_md, ocr_md, images, meta) -> entry
    async def list_entries() -> list[dict]
    async def get_entry(id) -> dict  # markdown + meta
    async def delete_entry(id) -> bool
    async def get_image_path(id, image_name) -> Path
    
    # 内部方法
    _generate_display_name(filename, existing_names) -> str  # 重名加后缀
    _extract_base64_images(markdown) -> (new_md, dict[name, bytes])  # 提取 base64
    _rewrite_image_paths(markdown, images_dict) -> (new_md, dict[name, bytes])  # OCR 图片路径重写
    _read_index() -> dict
    _write_index(data) -> None
```

### 1.2 `backend/app/api/routes/translations.py` — API 路由

```
GET  /api/translations              → list_entries()
GET  /api/translations/{id}         → get_entry(id)  
DELETE /api/translations/{id}       → delete_entry(id)
GET  /api/translations/{id}/images/{filename} → FileResponse
```

### 1.3 前端组件

- `frontend/src/components/HistoryList.tsx` — 历史记录列表组件
- 在 `Sidebar.tsx` 中新增 "历史" tab，渲染 HistoryList

## 2. 修改点

### 2.1 `backend/app/services/markdown_builder.py`

图片输出改为相对路径 + 返回图片 bytes 字典：

```python
# 之前: data:image/png;base64,xxx
# 之后: ./images/fig_1.png
# process() 返回 (markdown_str, images_dict)
```

### 2.2 `backend/app/services/ocr_service.py`

不再 base64 内嵌，改为返回 `(markdown, images_dict)`：
- `recognize()` 返回 `tuple[str, dict[str, bytes]]`
- OCR 图片直接传递 `OCRResult.images`
- markdown 中的图片路径统一重写为 `./images/xxx`

### 2.3 `backend/app/api/routes/pdf.py`

保存逻辑改为调用 `TranslationStore.save()`：
- 不再直接写 `Translation/{stem}.md`
- 返回值增加 `translation_id` 字段

### 2.4 `frontend/src/lib/api.ts`

新增：
```typescript
getTranslationList() → TranslationEntry[]
getTranslation(id) → { markdown, ocr_markdown, meta }
deleteTranslation(id) → void
```

### 2.5 `frontend/src/components/MarkdownViewer.tsx`

渲染前将 `./images/xxx` 替换为 `/api/translations/{id}/images/xxx`（通过 prop 传入 translationId）。

### 2.6 `frontend/src/app/page.tsx`

- 新增 `translationId` state
- 加载历史翻译时设置 translationId + markdown
- 新翻译完成后刷新历史列表

### 2.7 `frontend/src/components/Sidebar.tsx`

- 新增 "历史" tab
- 渲染 HistoryList 组件
- 点击回调传递到 page.tsx

## 3. 图片处理流程

### LLM 管线
```
MarkdownBuilder.process(parsed_pdf)
  → (markdown_with_relative_paths, {fig_1.png: bytes, fig_2.jpeg: bytes, ...})
  → TranslationStore.save() 写入 images/ 子目录
```

### OCR 管线
```
OCRService.recognize(file_bytes)
  → OCRResult {markdown, images: {path: bytes}}
  → 重命名图片为 fig_N.ext，重写 markdown 路径
  → TranslationStore.save() 写入 images/ 子目录
```

## 4. index.json 并发保护

```python
class TranslationStore:
    _lock = asyncio.Lock()
    
    async def _read_index(self):
        async with self._lock:
            # read file
    
    async def _update_index(self, updater_fn):
        async with self._lock:
            data = read()
            updater_fn(data)
            write(data)
```
