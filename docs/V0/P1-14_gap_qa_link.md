# P1-14: Gap → QA Chat 联动

## 依赖
- P1-13（Gap Engine 前端页面）
- P0-10（Chat 前端页）

## 目的
实现 Gap Engine 与 QA Chat 的联动功能：Gap Engine 检索到的论文自动共享到 QA Chat 索引，用户可从 Gap 结果页点击"追问"跳转到 QA Chat 并预填上下文。

## 执行方法
1. 后端论文共享：
   - 在 `src/maelstrom/services/doc_service.py` 中添加 `share_papers_to_qa(session_id: str, papers: list[PaperRecord])` 方法
   - Gap Engine 运行完成后，自动将有 pdf_url 的论文下载并索引到 paper-qa
   - 索引结果关联到同一 session_id
   - 添加 API：`POST /api/gap/run/{run_id}/share-to-qa` — 手动触发论文共享（如自动共享失败）
2. 前端"追问"按钮：
   - 在 `components/gap/GapCard.tsx` 中添加"追问"按钮
   - 点击后跳转到 `/chat?session_id=xxx&context=gap-{gap_id}`
   - Chat 页面检测 URL 参数，预填上下文（Gap title + summary 作为初始提示）
3. 前端论文共享状态：
   - GapCard 或 PaperList 中显示论文是否已索引到 QA Chat
   - 共享进度提示（正在索引 / 已完成 / 失败）

## 验收条件
- Gap Engine 完成后，检索到的论文（有 PDF）自动索引到 QA Chat
- QA Chat 中可对 Gap Engine 检索的论文提问
- "追问"按钮跳转到 Chat 页面并预填 Gap 上下文
- 论文共享状态在前端可见
- 共享失败时有明确提示，不阻塞 Gap 结果展示

## Unit Test
- `test_share_papers_to_qa`: mock paper-qa 索引，验证论文共享调用正确
- `test_share_filters_no_pdf`: 无 pdf_url 的论文不被共享
- `test_share_api_endpoint`: POST share-to-qa 返回共享结果
- `test_ask_button_navigation`: 点击"追问"按钮，验证跳转 URL 包含 session_id 和 context
- `test_chat_prefill_context`: Chat 页面检测 URL 参数，验证预填内容
- `test_share_failure_graceful`: 共享失败时 Gap 结果正常展示
