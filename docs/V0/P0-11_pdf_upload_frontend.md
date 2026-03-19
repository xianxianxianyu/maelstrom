# P0-11: PDF 上传前端组件

## 依赖
- P0-10（Chat 前端页）

## 目的
实现 PDF 文件上传前端组件，集成到 QA Chat 页面，让用户可以上传论文 PDF 并查看已索引文档列表。

## 执行方法
1. 创建 `components/chat/DocUploader.tsx`：
   - 拖拽上传区域（drag & drop）+ 点击选择文件
   - 文件类型限制（.pdf）
   - 文件大小限制提示（50MB）
   - 上传进度条
   - 上传完成后显示成功/失败状态
2. 创建文档列表展示：
   - 已索引文档列表（文件名、索引时间、大小）
   - 每个文档可删除（调用 DELETE /api/chat/docs/{doc_id}）
3. 集成到 `app/chat/page.tsx`：
   - Chat 页面侧边或顶部显示 DocUploader
   - 上传成功后自动刷新文档列表
4. API 调用：
   - 上传：POST /api/chat/docs/upload（multipart/form-data）
   - 列表：GET /api/chat/docs?session_id=xxx
   - 删除：DELETE /api/chat/docs/{doc_id}

## 验收条件
- 拖拽和点击两种方式均可上传 PDF
- 非 PDF 文件被拒绝并提示
- 上传过程显示进度
- 上传成功后文档出现在列表中
- 可删除已索引文档
- 上传失败显示错误信息

## Unit Test
- `test_uploader_renders`: 验证 DocUploader 渲染上传区域
- `test_file_type_filter`: 选择非 PDF 文件时显示拒绝提示
- `test_upload_success`: mock API，上传 PDF 后验证成功状态和列表刷新
- `test_upload_progress`: 验证上传过程中显示进度条
- `test_doc_list_display`: mock API，验证文档列表正确渲染
- `test_delete_doc`: 点击删除按钮，验证 DELETE 请求发出并列表更新
