# P2-01: 反问协议（Clarification Protocol）

## 依赖
- P2-00（IntentType.clarification_needed + ClassifiedIntent）
- P0-04（llm_client）

## 目的
当意图分类器返回 `clarification_needed` 时，系统不应沉默或猜测，而应主动生成结构化反问，引导用户明确意图。实现反问生成器 + 反问 Schema + 前端交互协议。

## 执行方法

### 1. 反问 Schema — `src/maelstrom/schemas/clarification.py`

```python
class ClarificationOption(BaseModel):
    label: str                    # 选项显示文本，如 "发现研究缺口"
    intent: IntentType            # 对应的意图
    description: str = ""         # 补充说明

class ClarificationRequest(BaseModel):
    request_id: str               # 唯一 ID
    question: str                 # 反问文本，如 "你想做什么？"
    options: list[ClarificationOption]  # 2-4 个选项
    allow_freetext: bool = True   # 是否允许用户自由输入
    original_input: str           # 用户原始输入
    session_id: str
```

### 2. 反问生成器 — `src/maelstrom/services/clarification_service.py`

两种模式：

**模式 A — 模板反问（fast-path）**：
当 LLM 分类器返回 confidence 在 0.4-0.6 之间，且有 top-2 候选意图时，直接用模板生成：
```
"我不太确定你的意图。你是想：
1. {option_1.label} — {option_1.description}
2. {option_2.label} — {option_2.description}
还是其他？"
```

**模式 B — LLM 反问（低 confidence 或无候选）**：
当 confidence < 0.4 或无明确候选时，调用 LLM 生成更自然的反问：
- System prompt：你是研究助手，用户输入不够明确，请生成一个友好的反问来澄清意图
- 输入：用户原始文本 + 会话上下文
- 输出：JSON `{"question": "...", "options": [...]}`

### 3. 反问解析器

用户回复反问后，需要解析回复：
- 如果用户选择了选项（前端传回 `option_index`）→ 直接映射到对应 IntentType
- 如果用户自由输入 → 重新走 `classify_intent`，但 `session_context.recent_intent` 设为 `clarification_needed`，避免无限反问循环
- 最多反问 1 次，第二次仍不明确时默认路由到 `qa_chat`

### 4. SSE 事件

反问通过 SSE 推送到前端：
```json
{
  "event": "clarification",
  "data": {
    "request_id": "clar-001",
    "question": "我不太确定你的意图...",
    "options": [...],
    "allow_freetext": true
  }
}
```

用户回复通过 POST 提交：
```
POST /api/chat/clarify
{
  "request_id": "clar-001",
  "option_index": 0       // 或 "freetext": "我想..."
}
```

## 验收条件
- ClarificationRequest 包含 question, options, allow_freetext 字段
- 模板反问在有 top-2 候选时正确生成
- LLM 反问在低 confidence 时正确生成
- 用户选择选项后正确映射到 IntentType
- 用户自由输入后重新分类
- 最多反问 1 次，不会无限循环
- SSE 事件格式正确

## Unit Test
- `test_clarification_schema`: 验证 ClarificationRequest / ClarificationOption 字段
- `test_template_clarification`: confidence=0.5 + 2 候选 → 模板反问包含 2 个选项
- `test_llm_clarification`: confidence=0.3 → LLM 生成反问（mock）
- `test_option_selection_resolves`: 选择 option_index=0 → 返回对应 IntentType
- `test_freetext_reclassify`: 自由输入 → 重新调用 classify_intent
- `test_max_one_clarification`: 第二次 clarification_needed → 默认 qa_chat
- `test_sse_event_format`: 验证 SSE 事件 JSON 格式正确
