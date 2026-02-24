"""AgentContext 数据类 — Agent 间共享的执行上下文

提供 Agent 间数据传递的统一上下文对象，包含任务标识、文件内容、
事件总线、术语表、翻译配置、翻译结果、质量报告和取消令牌。

Requirements: 5.5
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from backend.app.services.pipelines.base import CancellationToken
from backend.app.services.prompt_generator import PromptProfile

if TYPE_CHECKING:
    from agent.event_bus import EventBus
    from agent.models import QualityReport
    from backend.app.services.pdf_parser import ParsedPDF


@dataclass
class AgentContext:
    """Agent 间共享的执行上下文

    在翻译工作流中，OrchestratorAgent 创建 AgentContext 实例，
    各 Agent（OCR、Translation、Review、Terminology）通过该上下文共享数据，
    避免重复计算。

    Attributes:
        task_id: 翻译任务唯一标识
        filename: 上传的 PDF 文件名
        file_content: PDF 文件的原始字节内容
        event_bus: SSE 事件总线，用于推送进度事件
        enable_ocr: 是否启用 OCR 管线
        pipeline_type: OCRAgent 选定的管线类型 ("llm" | "ocr")
        parsed_pdf: LLM 管线解析后的结构化 PDF（OCRAgent 填充）
        glossary: 领域术语表 {英文术语: 中文翻译}
        prompt_profile: LLM 生成的翻译配置（含术语、领域、prompt）
        translated_md: 翻译后的 Markdown 文本
        quality_report: 审校 Agent 生成的质量报告
        paper_metadata: IndexAgent 提取的论文结构化元数据
        cancellation_token: 取消令牌，用于响应用户取消操作
    """

    task_id: str
    filename: str
    file_content: bytes
    event_bus: EventBus
    enable_ocr: bool = False
    pipeline_type: str = ""
    parsed_pdf: ParsedPDF | None = None
    glossary: dict[str, str] = field(default_factory=dict)
    prompt_profile: PromptProfile | None = None
    translated_md: str = ""
    images: dict[str, bytes] = field(default_factory=dict)
    ocr_md: str | None = None
    ocr_images: dict[str, bytes] = field(default_factory=dict)
    quality_report: QualityReport | None = None
    paper_metadata: dict = field(default_factory=dict)
    translation_id: str | None = None
    cancellation_token: CancellationToken = field(default_factory=CancellationToken)
