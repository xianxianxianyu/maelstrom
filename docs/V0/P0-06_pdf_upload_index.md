# P0-06: PDF 上传 + 索引 API

## 依赖
- P0-04（会话管理 API）
- P0-05（paper-qa 封装层）

## 目的
实现 PDF 文件上传、本地存储和 paper-qa 索引功能，让用户可以上传论文 PDF 并将其纳入 QA Chat 的知识库。

## 执行方法
1. 在 `src/maelstrom/api/docs.py` 中实现路由：
   - `POST /api/chat/docs/upload` — 接收 multipart/form-data（file + session_id），保存 PDF 到本地，调用 paper-qa 索引
   - `GET /api/chat/docs?session_id=xxx` — 列出当前会话已索引文档
   - `DELETE /api/chat/docs/{doc_id}` — 移除文档索引
2. 在 `src/maelstrom/services/doc_service.py` 中封装：
   - 文件保存到 `data/pdfs/{session_id}/{filename}`
   - 文件大小限制（V0: 50MB）
   - 文件类型校验（仅 .pdf）
   - 调用 `PaperQAService.index_document` 索引
   - 索引结果元数据写入 SQLite artifacts 表
3. 错误处理：文件过大 → 413，非 PDF → 415，索引失败 → 500 + 具体原因

## 验收条件
- 上传有效 PDF 返回 201 + 文档元数据（doc_id, filename, indexed_at）
- PDF 文件保存到正确的本地路径
- paper-qa 索引成功，文档可用于后续问答
- GET 列表返回当前会话所有已索引文档
- 非 PDF 文件上传返回 415
- 超大文件上传返回 413

## Unit Test
- `test_upload_pdf`: 上传有效 PDF，验证返回 201 和元数据
- `test_upload_non_pdf`: 上传 .txt 文件，验证返回 415
- `test_upload_too_large`: 上传超过 50MB 文件，验证返回 413
- `test_list_docs`: 上传 2 个 PDF 后 GET 列表，验证数量和字段
- `test_delete_doc`: 上传后 DELETE，验证 GET 列表不再包含
- `test_upload_invalid_session`: 使用不存在的 session_id 上传，验证返回 404
- `test_file_saved_to_disk`: 上传后验证文件存在于 `data/pdfs/{session_id}/` 目录
