# P2-06: Gap Followup — 基于 EvidenceMemory 的 Gap 追问增强

## 依赖
- P2-02（EvidenceMemory — search）
- P2-00（IntentType.gap_followup）
- P0-06（QA Chat — chat_service.start_ask）

## 目的
当用户追问某个 Gap（如"第二个 gap 能展开说说吗"），系统从 EvidenceMemory 中检索相关论文和 gap 信息，注入到 QA 问题的上下文中，让 paper-qa 能基于已有证据给出更精准的回答。

## 执行方法

### 1. Gap Followup 服务 — `src/maelstrom/services/gap_followup_service.py`

```python
async def enrich_gap_followup(
    session_id: str,
    user_input: str,
    gap_ref: str | None,
) -> str:
    """将 gap 追问增强为带上下文的 QA 问题"""
    evidence_memory = get_evidence_memory()

    # 1. 如果有明确的 gap_ref（如 "gap-003"），直接查询
    if gap_ref:
        hits = await evidence_memory.search(session_id, gap_ref, limit=5)
    else:
        # 2. 否则用用户输入做 FTS 搜索
        hits = await evidence_memory.search(session_id, user_input, limit=5)

    if not hits:
        return user_input  # 无上下文，原样返回

    # 3. 构建增强 prompt
    context_parts = []
    for hit in hits:
        context_parts.append(f"[{hit.source_type}] {hit.title}: {hit.snippet}")

    enriched = (
        f"基于以下已有研究上下文：\n"
        f"{''.join(context_parts)}\n\n"
        f"用户问题：{user_input}"
    )
    return enriched
```

### 2. Phase Router 集成

在 `phase_router.py` 的 `gap_followup` 分支中：
```python
if intent.intent == IntentType.gap_followup:
    enriched_question = await enrich_gap_followup(
        session_id, user_input, intent.extracted_gap_ref
    )
    msg_id = await start_ask(session_id, enriched_question)
    return RouterResponse(
        response_type="stream",
        stream_url=f"/api/chat/ask/{msg_id}/stream",
    )
```

### 3. Gap Ref 提取增强

在意图分类器的关键词规则中，增强 gap_ref 提取：
- 正则匹配 `gap-\d+` → 直接提取
- 匹配 "第N个" → 转换为 `gap-{N}`（需查询当前 session 的 gap 列表映射）
- 匹配 "最后一个 gap" → 查询最新 gap

## 验收条件
- gap_followup 意图时，QA 问题被注入 EvidenceMemory 上下文
- 有 gap_ref 时精确检索对应 gap 和相关论文
- 无 gap_ref 时用用户输入做模糊搜索
- 无匹配时原样传递用户输入（不报错）
- 增强后的问题格式正确，paper-qa 可正常处理

## Unit Test
- `test_enrich_with_gap_ref`: 有 gap_ref → 搜索结果注入到问题中
- `test_enrich_without_gap_ref`: 无 gap_ref → 用用户输入搜索
- `test_enrich_no_hits`: 无匹配 → 返回原始输入
- `test_enriched_format`: 增强后的问题包含 "基于以下已有研究上下文"
- `test_gap_ref_extraction_regex`: "gap-003" → extracted_gap_ref="gap-003"
- `test_gap_ref_extraction_ordinal`: "第二个 gap" → extracted_gap_ref 正确映射
- `test_router_gap_followup_enriched`: 端到端：gap_followup 意图 → enriched question → QA stream
