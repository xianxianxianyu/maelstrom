"""Unit tests for AgentContext dataclass.

Validates:
- AgentContext dataclass fields and defaults (Requirements 5.5)
- All required fields are present (task_id, filename, file_content, event_bus)
- Optional fields have correct defaults (glossary, prompt_profile, translated_md, quality_report, cancellation_token)
- CancellationToken is auto-created when not provided
"""

import pytest
from dataclasses import fields, asdict

from agent.context import AgentContext
from backend.app.services.pipelines.base import CancellationToken
from backend.app.services.prompt_generator import PromptProfile


class FakeEventBus:
    """Minimal stand-in for EventBus (not yet implemented, Task 1.3)."""
    pass


# ---------------------------------------------------------------------------
# AgentContext field tests
# ---------------------------------------------------------------------------

class TestAgentContextFields:
    """Tests for AgentContext dataclass field definitions."""

    def test_has_all_required_fields(self):
        """AgentContext must have exactly the specified fields."""
        field_names = [f.name for f in fields(AgentContext)]
        expected = [
            "task_id",
            "filename",
            "file_content",
            "event_bus",
            "enable_ocr",
            "glossary",
            "prompt_profile",
            "translated_md",
            "images",
            "ocr_md",
            "ocr_images",
            "quality_report",
            "cancellation_token",
        ]
        assert field_names == expected

    def test_required_fields_count(self):
        """AgentContext should have 13 fields total."""
        assert len(fields(AgentContext)) == 13


# ---------------------------------------------------------------------------
# AgentContext construction tests
# ---------------------------------------------------------------------------

class TestAgentContextConstruction:
    """Tests for creating AgentContext instances."""

    def test_create_with_required_fields_only(self):
        """Creating AgentContext with only required fields should use defaults for the rest."""
        bus = FakeEventBus()
        ctx = AgentContext(
            task_id="task-001",
            filename="paper.pdf",
            file_content=b"fake-pdf-bytes",
            event_bus=bus,
        )
        assert ctx.task_id == "task-001"
        assert ctx.filename == "paper.pdf"
        assert ctx.file_content == b"fake-pdf-bytes"
        assert ctx.event_bus is bus

    def test_default_glossary_is_empty_dict(self):
        """glossary should default to an empty dict."""
        ctx = AgentContext(
            task_id="t1",
            filename="f.pdf",
            file_content=b"",
            event_bus=FakeEventBus(),
        )
        assert ctx.glossary == {}
        assert isinstance(ctx.glossary, dict)

    def test_default_prompt_profile_is_none(self):
        """prompt_profile should default to None."""
        ctx = AgentContext(
            task_id="t1",
            filename="f.pdf",
            file_content=b"",
            event_bus=FakeEventBus(),
        )
        assert ctx.prompt_profile is None

    def test_default_translated_md_is_empty_string(self):
        """translated_md should default to an empty string."""
        ctx = AgentContext(
            task_id="t1",
            filename="f.pdf",
            file_content=b"",
            event_bus=FakeEventBus(),
        )
        assert ctx.translated_md == ""

    def test_default_quality_report_is_none(self):
        """quality_report should default to None."""
        ctx = AgentContext(
            task_id="t1",
            filename="f.pdf",
            file_content=b"",
            event_bus=FakeEventBus(),
        )
        assert ctx.quality_report is None

    def test_default_cancellation_token_is_created(self):
        """cancellation_token should default to a new CancellationToken instance."""
        ctx = AgentContext(
            task_id="t1",
            filename="f.pdf",
            file_content=b"",
            event_bus=FakeEventBus(),
        )
        assert isinstance(ctx.cancellation_token, CancellationToken)
        assert ctx.cancellation_token.is_cancelled is False

    def test_glossary_instances_are_independent(self):
        """Each AgentContext should get its own glossary dict (no shared mutable default)."""
        ctx1 = AgentContext(
            task_id="t1", filename="a.pdf", file_content=b"", event_bus=FakeEventBus()
        )
        ctx2 = AgentContext(
            task_id="t2", filename="b.pdf", file_content=b"", event_bus=FakeEventBus()
        )
        ctx1.glossary["transformer"] = "Transformer"
        assert ctx2.glossary == {}

    def test_cancellation_token_instances_are_independent(self):
        """Each AgentContext should get its own CancellationToken (no shared mutable default)."""
        ctx1 = AgentContext(
            task_id="t1", filename="a.pdf", file_content=b"", event_bus=FakeEventBus()
        )
        ctx2 = AgentContext(
            task_id="t2", filename="b.pdf", file_content=b"", event_bus=FakeEventBus()
        )
        ctx1.cancellation_token.cancel()
        assert ctx1.cancellation_token.is_cancelled is True
        assert ctx2.cancellation_token.is_cancelled is False


# ---------------------------------------------------------------------------
# AgentContext with explicit values
# ---------------------------------------------------------------------------

class TestAgentContextExplicitValues:
    """Tests for creating AgentContext with all fields explicitly set."""

    def test_create_with_all_fields(self):
        """AgentContext should accept all fields explicitly."""
        bus = FakeEventBus()
        token = CancellationToken()
        profile = PromptProfile(domain="NLP", terminology={"attention": "注意力"})
        glossary = {"transformer": "Transformer", "embedding": "嵌入"}

        ctx = AgentContext(
            task_id="task-full",
            filename="research.pdf",
            file_content=b"\x00\x01\x02",
            event_bus=bus,
            glossary=glossary,
            prompt_profile=profile,
            translated_md="# 翻译结果\n\n这是翻译后的文本。",
            quality_report=None,  # QualityReport not yet implemented
            cancellation_token=token,
        )

        assert ctx.task_id == "task-full"
        assert ctx.filename == "research.pdf"
        assert ctx.file_content == b"\x00\x01\x02"
        assert ctx.event_bus is bus
        assert ctx.glossary == {"transformer": "Transformer", "embedding": "嵌入"}
        assert ctx.prompt_profile is profile
        assert ctx.prompt_profile.domain == "NLP"
        assert ctx.translated_md == "# 翻译结果\n\n这是翻译后的文本。"
        assert ctx.quality_report is None
        assert ctx.cancellation_token is token

    def test_file_content_accepts_bytes(self):
        """file_content field should work with arbitrary byte content."""
        ctx = AgentContext(
            task_id="t1",
            filename="binary.pdf",
            file_content=b"%PDF-1.4 binary content \xff\xfe",
            event_bus=FakeEventBus(),
        )
        assert isinstance(ctx.file_content, bytes)
        assert b"%PDF-1.4" in ctx.file_content

    def test_translated_md_can_be_set(self):
        """translated_md should be mutable after creation."""
        ctx = AgentContext(
            task_id="t1",
            filename="f.pdf",
            file_content=b"",
            event_bus=FakeEventBus(),
        )
        assert ctx.translated_md == ""
        ctx.translated_md = "# Translated Content"
        assert ctx.translated_md == "# Translated Content"

    def test_glossary_can_be_updated(self):
        """glossary should be mutable after creation."""
        ctx = AgentContext(
            task_id="t1",
            filename="f.pdf",
            file_content=b"",
            event_bus=FakeEventBus(),
        )
        ctx.glossary["attention"] = "注意力"
        ctx.glossary["embedding"] = "嵌入"
        assert len(ctx.glossary) == 2
        assert ctx.glossary["attention"] == "注意力"
