# 翻译输出管理 — 实施任务

- [x] 1. 创建 `backend/app/services/translation_store.py` — 存储管理服务
- [x] 2. 修改 `backend/app/services/markdown_builder.py` — 图片改相对路径，返回 (str, dict)
- [x] 3. 修改 `backend/app/services/ocr_service.py` — 不再 base64 内嵌，返回 (str, dict)
- [x] 4. 修改 `backend/app/api/routes/pdf.py` — 保存逻辑改用 TranslationStore
- [x] 5. 创建 `backend/app/api/routes/translations.py` — 新 API 路由
- [x] 6. 修改 `backend/app/main.py` — 注册 translations 路由
- [x] 7. 前端 `types/index.ts` + `lib/api.ts` — 新增类型和 API 调用
- [x] 8. 创建 `frontend/src/components/HistoryList.tsx` — 历史列表组件
- [x] 9. 修改 `frontend/src/components/Sidebar.tsx` — 新增"历史"tab
- [x] 10. 修改 `frontend/src/app/page.tsx` — 集成历史加载 + 刷新
- [x] 11. 修改 `frontend/src/components/MarkdownViewer.tsx` — 图片路径重写
