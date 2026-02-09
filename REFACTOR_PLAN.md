# 项目架构审视与重构方案

## 一、核心问题诊断

### 1.1 `pdf.py` 为什么"卡"——God Route 反模式

`backend/app/api/routes/pdf.py` 是整个项目最大的痛点，约 400 行，承担了至少 6 种职责：

| 职责 | 行数 | 本应属于 |
|------|------|----------|
| Markdown 分段工具 `_split_md_segments()` | ~100 行 | 独立 service 或 utils |
| 文本块合并 `_merge_text_blocks()` | ~25 行 | `pdf_parser.py` 或独立 utils |
| LLM 管线编排 `llm_only_pipeline()` | ~60 行 | 独立 Pipeline 类 |
| OCR 管线编排 `ocr_translate_pipeline()` | ~70 行 | 独立 Pipeline 类 |
| 管线选择 + 结果保存逻辑 | ~60 行 | Pipeline Orchestrator |
| 路由定义（upload/cancel/tasks） | ~30 行 | 这才是路由该做的事 |

**后果**：
- 每次修改翻译逻辑都要碰这个巨大文件，认知负担重
- LLM 管线和 OCR 管线的代码高度相似（都有：提取摘要 → 生成 prompt → 并发翻译 → 后处理），但无法复用
- 测试困难——无法单独测试管线逻辑，必须通过 HTTP 请求触发
- 路由层直接 import 了 `LLMConfig`、`FunctionKey` 等 core 层对象，跨层耦合

### 1.2 Provider 实现重复度高

三个 Provider（GLM、OpenAI、DeepSeek）的 `translate()` 和 `chat()` 方法几乎一模一样：

```python
# OpenAI / DeepSeek 完全相同
response = await self.client.chat.completions.create(
    model=self.config.model,
    messages=[...],
    temperature=self.config.temperature,
    max_tokens=self.config.max_tokens,
)
return response.choices[0].message.content
```

- `OpenAIProvider` 和 `DeepSeekProvider` 唯一区别是 `base_url` 和 `AVAILABLE_MODELS`
- `GLMProvider` 唯一区别是用同步 SDK（`ZhipuAI`）而非 `AsyncOpenAI`

### 1.3 BaseService 抽象未被充分利用

`BaseService[T]` 定义了 `process()` 抽象方法，但：
- `TranslationService` 没有继承它
- `OCRService` 没有继承它
- `PostProcessor` 没有继承它
- `PromptGenerator` 是纯函数，没有类
- 只有 `PDFParser` 和 `MarkdownBuilder` 继承了

### 1.4 配置与运行时状态混杂

`pdf.py` 的 `upload_pdf()` 里直接操作 `LLMManager`：

```python
manager = get_llm_manager()
config = LLMConfig(provider=provider, model=model, api_key=actual_key)
manager.register(FunctionKey.TRANSLATION, config)
```

路由层不应该知道如何构造 `LLMConfig` 并注册到 Manager。这是 service 层的事。

### 1.5 Agent 系统与主系统割裂

`agent/` 目录有完整的 BaseAgent + Registry + QAAgent，但：
- 没有被任何 API 路由调用
- QAAgent 自己加载配置（`load_llm_configs()`），绕过了 backend 的 KeyStore 注入机制
- 前端有 `QAPanel` 组件，但没有对应的后端 QA 路由

### 1.6 其他问题

- `TranslationService.SYSTEM_PROMPT` 硬编码了默认 prompt，与 `prompt_generator.py` 的动态 prompt 功能重叠
- `translation_store.py` 用正则提取 base64 图片，逻辑复杂且与存储职责不符
- 前端 `api.ts` 的 `API_BASE` 默认端口 3301，但旧 README 写的 8000/3000，容易混淆（已修正）


## 二、重构方案

### 2.1 拆解 pdf.py —— Pipeline 模式

这是最高优先级的改动。将 `pdf.py` 从 400 行的 God Route 拆成清晰的分层结构：

```
backend/app/
├── api/routes/
│   └── pdf.py                  # 瘦路由：只做参数校验 + 调用 orchestrator + 返回响应
├── services/
│   ├── pipelines/
│   │   ├── __init__.py
│   │   ├── base.py             # BasePipeline 抽象类
│   │   ├── llm_pipeline.py     # LLM 管线：PyMuPDF → 翻译 → Markdown
│   │   ├── ocr_pipeline.py     # OCR 管线：OCR → 分段 → 翻译 → 重组
│   │   └── orchestrator.py     # PipelineOrchestrator：选择管线 + 执行 + 保存结果
│   ├── text_processing.py      # 从 pdf.py 提取：_split_md_segments + _merge_text_blocks
│   └── ...（现有 services 不变）
```

#### BasePipeline 设计

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from app.services.prompt_generator import PromptProfile

@dataclass
class PipelineResult:
    """管线统一输出"""
    translated_md: str
    images: dict[str, bytes]
    ocr_md: Optional[str] = None
    ocr_images: dict[str, bytes] = None
    prompt_profile: Optional[PromptProfile] = None

class BasePipeline(ABC):
    """翻译管线抽象基类"""

    def __init__(self, translator, system_prompt: str = None):
        self.translator = translator
        self.system_prompt = system_prompt
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @abstractmethod
    async def execute(self, file_content: bytes, filename: str) -> PipelineResult:
        """执行管线，返回统一结果"""
        pass
```

#### PipelineOrchestrator 设计

```python
class PipelineOrchestrator:
    """管线编排器 — 路由层唯一需要调用的入口"""

    async def process(
        self,
        file_content: bytes,
        filename: str,
        provider: str,
        model: str,
        api_key: str,
        enable_ocr: bool = False,
        system_prompt: str = None,
    ) -> PipelineResult:
        # 1. 配置 LLM
        self._setup_llm(provider, model, api_key)
        # 2. 选择管线
        pipeline = self._select_pipeline(enable_ocr, system_prompt)
        # 3. 创建任务 + 执行
        result = await pipeline.execute(file_content, filename)
        # 4. 保存结果
        entry = await self._save_result(filename, result, provider, model, enable_ocr)
        return result, entry
```

#### 重构后的 pdf.py（目标 < 60 行）

```python
@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    provider: str = Form("zhipuai"),
    model: str = Form("glm-4"),
    api_key: str | None = Form(None),
    system_prompt: str | None = Form(None),
    enable_ocr: bool = Form(False),
):
    # 参数校验
    validate_pdf(file)
    actual_key = get_api_key(provider, api_key)
    if not actual_key:
        raise HTTPException(400, f"API key required for: {provider}")

    # 委托给 orchestrator
    content = await file.read()
    orchestrator = PipelineOrchestrator()
    result, entry = await orchestrator.process(
        content, file.filename, provider, model, actual_key, enable_ocr, system_prompt
    )

    return build_response(result, entry, model)
```

### 2.2 合并 Provider 实现 —— OpenAI 兼容基类

```
core/providers/
├── base.py                  # BaseProvider（不变）
├── openai_compat.py         # 新增：OpenAI 兼容基类
├── glm.py                   # 继承 OpenAICompatProvider 或保持独立
├── openai.py                # 继承 OpenAICompatProvider，只设 MODELS + base_url
└── deepseek.py              # 继承 OpenAICompatProvider，只设 MODELS + base_url
```

```python
class OpenAICompatProvider(BaseProvider):
    """所有 OpenAI 兼容 API 的基类（DeepSeek、OpenAI、Moonshot 等）"""

    DEFAULT_BASE_URL: str = ""  # 子类覆盖
    AVAILABLE_MODELS: list[ModelInfo] = []  # 子类覆盖

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url or self.DEFAULT_BASE_URL,
        )

    async def translate(self, text: str, system_prompt: str) -> str:
        return await self._chat_completion([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ])

    async def chat(self, messages: list[dict]) -> str:
        return await self._chat_completion(messages)

    async def _chat_completion(self, messages: list[dict]) -> str:
        response = await self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        return response.choices[0].message.content

    def get_available_models(self) -> list[ModelInfo]:
        return self.AVAILABLE_MODELS
```

重构后 `DeepSeekProvider` 只需：

```python
class DeepSeekProvider(OpenAICompatProvider):
    DEFAULT_BASE_URL = "https://api.deepseek.com"
    AVAILABLE_MODELS = [
        ModelInfo("deepseek-chat", "DeepSeek Chat", "deepseek", "General conversation"),
        ModelInfo("deepseek-reasoner", "DeepSeek Reasoner", "deepseek", "Advanced reasoning"),
    ]

    @property
    def provider_name(self) -> str:
        return "deepseek"
```

新增 Provider（如 Moonshot、Qwen）只需 5-10 行代码。

### 2.3 统一 Service 层接口

当前 `BaseService` 只被 2 个类使用。建议：

**方案 A（推荐）：去掉 BaseService，改用 Protocol**

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Translatable(Protocol):
    async def translate(self, text: str, system_prompt: str) -> str: ...

@runtime_checkable
class Processable(Protocol):
    def process(self, text: str) -> str: ...
```

这样 Pipeline 只依赖协议，不依赖具体类，更 Pythonic。

**方案 B：让所有 Service 继承 BaseService**

如果偏好 OOP 风格，则让 `TranslationService`、`OCRService`、`PostProcessor` 都继承 `BaseService`。但 Python 社区更倾向 Protocol。

### 2.4 Agent 系统接入主系统

```
backend/app/api/routes/
└── agent.py                 # 新增：Agent API 路由

# 端点设计
POST /api/agent/qa          # 问答（调用 QAAgent）
GET  /api/agent/list         # 列出可用 Agent
```

关键改动：
- QAAgent 不再自己加载配置，而是通过 `LLMManager`（已注入 KeyStore）获取实例
- 前端 `QAPanel` 调用 `/api/agent/qa` 而非直接调用 LLM

### 2.5 配置层优化

当前 `pdf.py` 路由里直接构造 `LLMConfig` 并注册到 Manager，应该下沉到 service 层：

```python
# backend/app/services/llm_setup.py
class LLMSetupService:
    """封装 LLM 配置的运行时注册逻辑"""

    @staticmethod
    def ensure_translation_ready(provider: str, model: str, api_key: str):
        """确保 translation 功能键已绑定到正确的 LLM 配置"""
        manager = get_llm_manager()
        config = LLMConfig(provider=provider, model=model, api_key=api_key)
        manager.register(FunctionKey.TRANSLATION, config)
```

路由层只需调用 `LLMSetupService.ensure_translation_ready(provider, model, key)`。

### 2.6 图片处理抽离

`translation_store.py` 里的 base64 图片提取逻辑（`_extract_base64_images`）应该移到独立的图片处理模块：

```python
# backend/app/services/image_utils.py
class ImageExtractor:
    """从 Markdown 中提取 base64 图片，替换为相对路径"""

    @staticmethod
    def extract_and_replace(markdown: str) -> tuple[str, dict[str, bytes]]:
        ...
```

`TranslationStore` 只负责文件 I/O 和索引管理。


## 三、优先级排序与实施计划

### Phase 1：拆解 pdf.py（高优先级，解决"卡"的根源）

| 步骤 | 任务 | 预期效果 |
|------|------|----------|
| 1.1 | 创建 `services/text_processing.py`，将 `_split_md_segments` 和 `_merge_text_blocks` 移入 | pdf.py 减少 ~130 行 |
| 1.2 | 创建 `services/pipelines/base.py`，定义 `BasePipeline` + `PipelineResult` | 建立管线抽象 |
| 1.3 | 创建 `services/pipelines/llm_pipeline.py`，将 `llm_only_pipeline()` 提取为 `LLMPipeline` 类 | 可独立测试 |
| 1.4 | 创建 `services/pipelines/ocr_pipeline.py`，将 `ocr_translate_pipeline()` 提取为 `OCRPipeline` 类 | 可独立测试 |
| 1.5 | 创建 `services/pipelines/orchestrator.py`，封装管线选择 + 任务管理 + 结果保存 | 路由层彻底解耦 |
| 1.6 | 重写 `pdf.py`，只保留路由定义 + 参数校验 + 调用 orchestrator | 目标 < 80 行 |

### Phase 2：Provider 合并（中优先级，减少重复代码）

| 步骤 | 任务 | 预期效果 |
|------|------|----------|
| 2.1 | 创建 `core/providers/openai_compat.py` | 统一 OpenAI 兼容 API 调用 |
| 2.2 | 重写 `openai.py` 和 `deepseek.py`，继承 `OpenAICompatProvider` | 每个 Provider < 15 行 |
| 2.3 | 处理 `glm.py`（ZhipuAI SDK 是同步的，需要 `asyncio.to_thread` 包装或保持独立） | GLM 也走统一接口 |

### Phase 3：Agent 接入（中优先级，完善功能闭环）

| 步骤 | 任务 | 预期效果 |
|------|------|----------|
| 3.1 | 创建 `backend/app/api/routes/agent.py`，暴露 QA 端点 | 前端 QAPanel 可用 |
| 3.2 | 修改 `QAAgent`，通过 `LLMManager` 获取实例（不再自己加载配置） | 统一 Key 管理 |
| 3.3 | 前端 `QAPanel` 对接 `/api/agent/qa` | 功能闭环 |

### Phase 4：Service 层清理（低优先级，代码质量提升）

| 步骤 | 任务 | 预期效果 |
|------|------|----------|
| 4.1 | 创建 `services/llm_setup.py`，封装 LLM 运行时配置逻辑 | 路由不再直接操作 Manager |
| 4.2 | 创建 `services/image_utils.py`，抽离 base64 图片处理 | TranslationStore 职责单一 |
| 4.3 | 评估 `BaseService` 的去留（推荐改用 Protocol） | 更 Pythonic |
| 4.4 | `TranslationService.SYSTEM_PROMPT` 改为 fallback，优先使用 `prompt_generator` 的动态 prompt | 消除重叠 |

## 四、重构前后对比

### pdf.py 行数

| | 重构前 | 重构后 |
|--|--------|--------|
| `pdf.py` | ~400 行 | ~80 行 |
| 新增 `text_processing.py` | - | ~130 行 |
| 新增 `pipelines/base.py` | - | ~40 行 |
| 新增 `pipelines/llm_pipeline.py` | - | ~80 行 |
| 新增 `pipelines/ocr_pipeline.py` | - | ~90 行 |
| 新增 `pipelines/orchestrator.py` | - | ~80 行 |

总代码量略有增加，但每个文件职责单一、可独立测试、可独立修改。

### Provider 代码量

| | 重构前 | 重构后 |
|--|--------|--------|
| `openai.py` | ~50 行 | ~15 行 |
| `deepseek.py` | ~55 行 | ~15 行 |
| `glm.py` | ~50 行 | ~30 行（同步 SDK 需额外处理） |
| 新增 `openai_compat.py` | - | ~50 行 |
| 新增 Provider 成本 | ~50 行/个 | ~10 行/个 |

## 五、风险与注意事项

1. **Phase 1 是最大改动**，建议先写好 Pipeline 的单元测试再动手拆
2. **GLM 的同步 SDK** 是个坑——`ZhipuAI` 没有 async 版本，当前代码在 async 函数里直接调用同步方法会阻塞事件循环。应该用 `asyncio.to_thread()` 包装，或者换用 OpenAI 兼容接口（智谱也支持）
3. **任务取消机制** 在拆分 Pipeline 后需要重新设计——建议 Pipeline 接收一个 `CancellationToken` 而非直接检查 `task_info.cancelled`
4. **前端不需要改动**（Phase 1-2），API 接口保持不变
