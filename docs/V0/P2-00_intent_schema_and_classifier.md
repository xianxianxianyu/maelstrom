# P2-00: 意图 Schema + 意图分类器（关键词 fast-path + LLM fallback）

## 依赖
- P0-01（Pydantic Schema）
- P0-04（LLM 配置 + llm_client）

## 目的
定义用户输入的意图分类体系，实现两级分类器：关键词规则 fast-path 优先匹配，未命中时 fallback 到 LLM 分类。这是 Phase Router 的核心决策组件。

## 意图类型

| Intent | 含义 | 典型触发 |
|--------|------|----------|
| `gap_discovery` | 用户想发现研究缺口 | "帮我分析 X 领域的研究空白" |
| `qa_chat` | 用户想对已有文档提问 | "这篇论文的方法是什么？" |
| `gap_followup` | 用户想追问已有 Gap 结果 | "第二个 gap 能展开说说吗？" |
| `share_to_qa` | 用户想把 Gap 论文导入 QA | "把这些论文加到问答里" |
| `config` | 用户想配置 LLM / 系统设置 | "切换到 Claude 模型" |
| `clarification_needed` | 分类器无法确定意图 | 模糊输入 |

## 执行方法

### 1. 意图 Schema — `src/maelstrom/schemas/intent.py`

```python
class IntentType(str, Enum):
    gap_discovery = "gap_discovery"
    qa_chat = "qa_chat"
    gap_followup = "gap_followup"
    share_to_qa = "share_to_qa"
    config = "config"
    clarification_needed = "clarification_needed"

class ClassifiedIntent(BaseModel):
    intent: IntentType
    confidence: float = Field(ge=0, le=1)
    extracted_topic: str | None = None       # gap_discovery 时提取的主题
    extracted_gap_ref: str | None = None     # gap_followup 时引用的 gap ID
    reasoning: str = ""                       # LLM 分类时的推理过程
    classifier_source: Literal["keyword", "llm"] = "keyword"
```

### 2. 关键词分类器 — `src/maelstrom/services/intent_classifier.py`

规则引擎（fast-path）：
- `gap_discovery`: 包含 "研究空白|research gap|gap analysis|缺口|空白|survey|综述|领域分析|研究方向" 等关键词，且长度 ≥ 10 字符
- `qa_chat`: 包含 "这篇|论文|paper|文档|PDF|引用|摘要" 等关键词，或以 "?" / "？" 结尾且长度 < 50
- `gap_followup`: 包含 "gap-" 或 "第N个gap" 或 "展开|详细|elaborate" 等模式
- `share_to_qa`: 包含 "导入|share|加到问答|加入QA" 等关键词
- `config`: 包含 "配置|设置|切换模型|config|setting|API key" 等关键词

规则匹配时 confidence = 0.85，未匹配时 fallback 到 LLM。

### 3. LLM 分类器 — 同文件

当关键词未命中时，调用 `call_llm` 进行分类：
- System prompt 包含意图定义表 + 当前会话上下文摘要
- 要求 LLM 输出 JSON：`{"intent": "...", "confidence": 0.0-1.0, "extracted_topic": "...", "reasoning": "..."}`
- 解析 LLM 输出，confidence < 0.6 时强制设为 `clarification_needed`
- LLM 调用超时 10s，超时时返回 `clarification_needed`

### 4. 统一入口函数

```python
async def classify_intent(
    user_input: str,
    session_context: SessionContext | None = None,
) -> ClassifiedIntent:
    # 1. 关键词 fast-path
    result = _keyword_classify(user_input)
    if result is not None:
        return result
    # 2. LLM fallback
    return await _llm_classify(user_input, session_context)
```

`SessionContext` 是一个轻量结构，包含：
- `session_id`
- `has_gap_runs: bool`（是否有已完成的 gap run）
- `has_indexed_docs: bool`（是否有已索引文档）
- `recent_intent: IntentType | None`（上一轮意图，辅助上下文判断）

## 验收条件
- `IntentType` 枚举包含 6 种意图
- `ClassifiedIntent` 包含 intent, confidence, extracted_topic, classifier_source 字段
- 关键词分类器对明确输入返回正确意图，confidence = 0.85
- 关键词未命中时正确 fallback 到 LLM 分类
- LLM 分类器输出可解析为 ClassifiedIntent
- confidence < 0.6 时返回 clarification_needed
- LLM 超时时返回 clarification_needed 而非挂起

## Unit Test
- `test_intent_schema`: 验证 IntentType 包含 6 种意图
- `test_classified_intent_fields`: 验证 ClassifiedIntent 字段完整
- `test_keyword_gap_discovery`: "帮我分析 NLP 领域的研究空白" → gap_discovery
- `test_keyword_qa_chat`: "这篇论文的方法是什么？" → qa_chat
- `test_keyword_gap_followup`: "第二个 gap 能展开说说吗" → gap_followup
- `test_keyword_share_to_qa`: "把这些论文加到问答里" → share_to_qa
- `test_keyword_config`: "切换到 Claude 模型" → config
- `test_keyword_miss_fallback_llm`: 模糊输入 "我想了解 transformer" → 调用 LLM（mock）
- `test_llm_low_confidence_clarification`: LLM 返回 confidence=0.4 → clarification_needed
- `test_llm_timeout_clarification`: LLM 超时 → clarification_needed
- `test_session_context_influence`: 有 gap_runs 时 "展开说说" → gap_followup（上下文辅助）
