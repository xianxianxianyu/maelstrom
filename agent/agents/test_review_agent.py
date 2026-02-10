"""Tests for ReviewAgent

Unit tests covering:
- Registration in agent_registry
- _check_terminology_consistency with crafted markdown
- _check_format_integrity (broken tables, unclosed math, broken headings, missing images)
- _detect_untranslated (English paragraphs, code block exclusion, LaTeX exclusion)
- _build_quality_report scoring logic
- Full run() flow
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from agent.agents.review_agent import ReviewAgent
from agent.context import AgentContext
from agent.event_bus import EventBus
from agent.models import FormatIssue, QualityReport, TermIssue
from agent.registry import agent_registry
from backend.app.services.pipelines.base import CancellationToken


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def event_bus():
    """Create a fresh EventBus."""
    return EventBus()


@pytest.fixture
def agent():
    """Create a ReviewAgent instance."""
    return ReviewAgent()


@pytest_asyncio.fixture
async def ctx(event_bus):
    """Create a minimal AgentContext for testing."""
    return AgentContext(
        task_id="test-review-001",
        filename="test.pdf",
        file_content=b"%PDF-1.4 fake content",
        event_bus=event_bus,
        glossary={"Transformer": "变换器", "attention": "注意力"},
        translated_md="",
    )


# ---------------------------------------------------------------------------
# Tests: Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    """Verify ReviewAgent is registered in agent_registry."""

    def test_registered_in_registry(self):
        """ReviewAgent should be registered under its class name."""
        assert agent_registry.get("ReviewAgent") is ReviewAgent

    def test_name_property(self, agent: ReviewAgent):
        """name property should return 'review'."""
        assert agent.name == "review"

    def test_description_property(self, agent: ReviewAgent):
        """description property should be non-empty."""
        assert agent.description
        assert isinstance(agent.description, str)


# ---------------------------------------------------------------------------
# Tests: _check_terminology_consistency
# ---------------------------------------------------------------------------


class TestCheckTerminologyConsistency:
    """Test terminology consistency checking."""

    def test_no_issues_when_consistent(self, agent: ReviewAgent):
        """No issues when all terms use the expected translation."""
        text = (
            "Transformer 是一种变换器模型。\n"
            "attention 机制即注意力机制。\n"
        )
        glossary = {"Transformer": "变换器", "attention": "注意力"}
        issues = agent._check_terminology_consistency(text, glossary)
        assert len(issues) == 0

    def test_detects_inconsistent_translation(self, agent: ReviewAgent):
        """Should detect when a term has multiple translations."""
        text = (
            "Transformer 是一种变换器模型。\n"
            "Transformer 也被称为转换器架构。\n"
        )
        glossary = {"Transformer": "变换器"}
        issues = agent._check_terminology_consistency(text, glossary)
        assert len(issues) >= 1
        issue = issues[0]
        assert issue.english_term == "Transformer"
        assert len(issue.translations) >= 2
        assert issue.suggested == "变换器"

    def test_case_insensitive_matching(self, agent: ReviewAgent):
        """English term matching should be case-insensitive."""
        text = (
            "transformer 是一种变换器模型。\n"
            "TRANSFORMER 也被称为转换器架构。\n"
        )
        glossary = {"Transformer": "变换器"}
        issues = agent._check_terminology_consistency(text, glossary)
        assert len(issues) >= 1

    def test_empty_text_returns_no_issues(self, agent: ReviewAgent):
        """Empty text should return no issues."""
        issues = agent._check_terminology_consistency("", {"term": "翻译"})
        assert issues == []

    def test_empty_glossary_returns_no_issues(self, agent: ReviewAgent):
        """Empty glossary should return no issues."""
        issues = agent._check_terminology_consistency("Some text", {})
        assert issues == []

    def test_locations_are_tracked(self, agent: ReviewAgent):
        """Issue locations should reference line numbers."""
        text = (
            "Line 1: Transformer 变换器\n"
            "Line 2: some other text\n"
            "Line 3: Transformer 转换器\n"
        )
        glossary = {"Transformer": "变换器"}
        issues = agent._check_terminology_consistency(text, glossary)
        assert len(issues) >= 1
        # Locations should contain line references
        for loc in issues[0].locations:
            assert "Line" in loc


# ---------------------------------------------------------------------------
# Tests: _check_format_integrity
# ---------------------------------------------------------------------------


class TestCheckFormatIntegrity:
    """Test format integrity checking."""

    def test_no_issues_with_valid_markdown(self, agent: ReviewAgent):
        """Valid markdown should produce no format issues."""
        text = (
            "# 标题\n\n"
            "## 子标题\n\n"
            "这是正文。\n\n"
            "| A | B |\n"
            "|---|---|\n"
            "| 1 | 2 |\n\n"
            "公式 $E=mc^2$ 在这里。\n"
        )
        issues = agent._check_format_integrity(text)
        assert len(issues) == 0

    def test_detects_broken_table(self, agent: ReviewAgent):
        """Should detect table with inconsistent column counts."""
        text = (
            "| A | B | C |\n"
            "|---|---|---|\n"
            "| 1 | 2 |\n"  # Missing column
        )
        issues = agent._check_format_integrity(text)
        table_issues = [i for i in issues if i.issue_type == "broken_table"]
        assert len(table_issues) >= 1

    def test_detects_unclosed_display_math(self, agent: ReviewAgent):
        """Should detect unmatched $$ delimiter."""
        text = (
            "Some text\n"
            "$$\n"
            "E = mc^2\n"
            "More text without closing delimiter\n"
        )
        issues = agent._check_format_integrity(text)
        math_issues = [i for i in issues if i.issue_type == "missing_formula"]
        assert len(math_issues) >= 1

    def test_detects_unclosed_inline_math(self, agent: ReviewAgent):
        """Should detect unmatched $ delimiter."""
        text = "The formula $E=mc^2 is important.\n"
        issues = agent._check_format_integrity(text)
        math_issues = [i for i in issues if i.issue_type == "missing_formula"]
        assert len(math_issues) >= 1

    def test_detects_broken_heading_levels(self, agent: ReviewAgent):
        """Should detect heading level jumps."""
        text = (
            "# Title\n\n"
            "### Subsection\n\n"  # Skips level 2
            "Some text.\n"
        )
        issues = agent._check_format_integrity(text)
        heading_issues = [i for i in issues if i.issue_type == "broken_heading"]
        assert len(heading_issues) >= 1
        assert "1" in heading_issues[0].description
        assert "3" in heading_issues[0].description

    def test_detects_missing_image_path(self, agent: ReviewAgent):
        """Should detect image references with empty paths."""
        text = "Here is an image: ![alt text]()\n"
        issues = agent._check_format_integrity(text)
        image_issues = [i for i in issues if i.issue_type == "missing_image"]
        assert len(image_issues) >= 1

    def test_valid_image_no_issue(self, agent: ReviewAgent):
        """Valid image reference should not produce issues."""
        text = "![diagram](images/fig1.png)\n"
        issues = agent._check_format_integrity(text)
        image_issues = [i for i in issues if i.issue_type == "missing_image"]
        assert len(image_issues) == 0

    def test_empty_text_returns_no_issues(self, agent: ReviewAgent):
        """Empty text should return no format issues."""
        issues = agent._check_format_integrity("")
        assert issues == []

    def test_consecutive_headings_no_skip(self, agent: ReviewAgent):
        """Consecutive heading levels (1→2→3) should not produce issues."""
        text = (
            "# Title\n\n"
            "## Section\n\n"
            "### Subsection\n\n"
        )
        issues = agent._check_format_integrity(text)
        heading_issues = [i for i in issues if i.issue_type == "broken_heading"]
        assert len(heading_issues) == 0


# ---------------------------------------------------------------------------
# Tests: _detect_untranslated
# ---------------------------------------------------------------------------


class TestDetectUntranslated:
    """Test untranslated paragraph detection."""

    def test_detects_english_paragraph(self, agent: ReviewAgent):
        """Should detect a block of 3+ consecutive English lines."""
        text = (
            "这是中文段落。\n\n"
            "This is an untranslated English paragraph that spans\n"
            "multiple lines and should be detected by the review\n"
            "agent as needing translation into Chinese.\n\n"
            "这是另一个中文段落。\n"
        )
        untranslated = agent._detect_untranslated(text)
        assert len(untranslated) >= 1
        assert "untranslated" in untranslated[0].lower()

    def test_excludes_code_blocks(self, agent: ReviewAgent):
        """Code blocks should not be flagged as untranslated."""
        text = (
            "这是中文。\n\n"
            "```python\n"
            "def hello():\n"
            "    print('Hello world')\n"
            "    return True\n"
            "```\n\n"
            "这是中文。\n"
        )
        untranslated = agent._detect_untranslated(text)
        assert len(untranslated) == 0

    def test_excludes_latex_blocks(self, agent: ReviewAgent):
        """LaTeX display blocks should not be flagged as untranslated."""
        text = (
            "这是中文。\n\n"
            "$$\n"
            "E = mc^2\n"
            "F = ma\n"
            "P = IV\n"
            "$$\n\n"
            "这是中文。\n"
        )
        untranslated = agent._detect_untranslated(text)
        assert len(untranslated) == 0

    def test_excludes_short_lines(self, agent: ReviewAgent):
        """Short single-word lines should not trigger detection."""
        text = (
            "这是中文。\n\n"
            "Transformer\n"
            "这是中文。\n"
        )
        untranslated = agent._detect_untranslated(text)
        assert len(untranslated) == 0

    def test_empty_text_returns_empty(self, agent: ReviewAgent):
        """Empty text should return no untranslated paragraphs."""
        untranslated = agent._detect_untranslated("")
        assert untranslated == []

    def test_all_chinese_returns_empty(self, agent: ReviewAgent):
        """Fully translated text should return no untranslated paragraphs."""
        text = (
            "这是第一段中文文本。\n"
            "这是第二段中文文本。\n"
            "这是第三段中文文本。\n"
        )
        untranslated = agent._detect_untranslated(text)
        assert len(untranslated) == 0

    def test_mixed_lines_not_flagged(self, agent: ReviewAgent):
        """Lines with both English and Chinese should not be flagged."""
        text = (
            "Transformer 是一种变换器模型。\n"
            "Attention 机制即注意力机制。\n"
            "BERT 是一种预训练模型。\n"
        )
        untranslated = agent._detect_untranslated(text)
        assert len(untranslated) == 0


# ---------------------------------------------------------------------------
# Tests: _build_quality_report
# ---------------------------------------------------------------------------


class TestBuildQualityReport:
    """Test quality report generation and scoring."""

    def test_perfect_score_no_issues(self, agent: ReviewAgent):
        """No issues should produce a score of 100."""
        report = agent._build_quality_report([], [], [])
        assert report.score == 100
        assert report.terminology_issues == []
        assert report.format_issues == []
        assert report.untranslated == []
        assert report.timestamp != ""

    def test_term_issues_deduct_5_each(self, agent: ReviewAgent):
        """Each terminology issue should deduct 5 points."""
        term_issues = [
            TermIssue(english_term="term1", translations=["a", "b"], suggested="a"),
            TermIssue(english_term="term2", translations=["c", "d"], suggested="c"),
        ]
        report = agent._build_quality_report(term_issues, [], [])
        assert report.score == 90  # 100 - 2*5

    def test_format_issues_deduct_3_each(self, agent: ReviewAgent):
        """Each format issue should deduct 3 points."""
        format_issues = [
            FormatIssue(issue_type="broken_table", location="Line 1", description="test"),
            FormatIssue(issue_type="missing_formula", location="Line 5", description="test"),
            FormatIssue(issue_type="broken_heading", location="Line 10", description="test"),
        ]
        report = agent._build_quality_report([], format_issues, [])
        assert report.score == 91  # 100 - 3*3

    def test_untranslated_deduct_2_each(self, agent: ReviewAgent):
        """Each untranslated paragraph should deduct 2 points."""
        untranslated = ["paragraph 1", "paragraph 2", "paragraph 3", "paragraph 4"]
        report = agent._build_quality_report([], [], untranslated)
        assert report.score == 92  # 100 - 4*2

    def test_combined_deductions(self, agent: ReviewAgent):
        """Combined issues should deduct correctly."""
        term_issues = [
            TermIssue(english_term="t1", translations=["a", "b"], suggested="a"),
        ]
        format_issues = [
            FormatIssue(issue_type="broken_table", location="L1", description="test"),
        ]
        untranslated = ["para1"]
        report = agent._build_quality_report(term_issues, format_issues, untranslated)
        assert report.score == 90  # 100 - 5 - 3 - 2

    def test_score_clamped_to_zero(self, agent: ReviewAgent):
        """Score should not go below 0."""
        # 25 term issues = 125 points deducted
        term_issues = [
            TermIssue(english_term=f"term{i}", translations=["a", "b"], suggested="a")
            for i in range(25)
        ]
        report = agent._build_quality_report(term_issues, [], [])
        assert report.score == 0

    def test_suggestions_generated_for_term_issues(self, agent: ReviewAgent):
        """Suggestions should be generated when term issues exist."""
        term_issues = [
            TermIssue(
                english_term="Transformer",
                translations=["变换器", "转换器"],
                suggested="变换器",
            ),
        ]
        report = agent._build_quality_report(term_issues, [], [])
        assert len(report.suggestions) >= 1
        assert any("术语" in s for s in report.suggestions)

    def test_suggestions_generated_for_format_issues(self, agent: ReviewAgent):
        """Suggestions should be generated when format issues exist."""
        format_issues = [
            FormatIssue(issue_type="broken_table", location="L1", description="test"),
        ]
        report = agent._build_quality_report([], format_issues, [])
        assert len(report.suggestions) >= 1
        assert any("格式" in s for s in report.suggestions)

    def test_suggestions_generated_for_untranslated(self, agent: ReviewAgent):
        """Suggestions should be generated when untranslated paragraphs exist."""
        report = agent._build_quality_report([], [], ["English paragraph"])
        assert len(report.suggestions) >= 1
        assert any("未翻译" in s for s in report.suggestions)

    def test_timestamp_is_set(self, agent: ReviewAgent):
        """Report timestamp should be a non-empty ISO format string."""
        report = agent._build_quality_report([], [], [])
        assert report.timestamp
        # Should be parseable as ISO format
        assert "T" in report.timestamp


# ---------------------------------------------------------------------------
# Tests: Full run() flow
# ---------------------------------------------------------------------------


class TestRunFlow:
    """Test the complete run() method."""

    @pytest.mark.asyncio
    async def test_run_sets_quality_report(
        self, agent: ReviewAgent, ctx: AgentContext
    ):
        """run() should set ctx.quality_report."""
        ctx.translated_md = "这是一段完整的中文翻译文本。\n"
        result = await agent.run(ctx)
        assert result.quality_report is not None
        assert isinstance(result.quality_report, QualityReport)
        assert ctx.quality_report is result.quality_report

    @pytest.mark.asyncio
    async def test_run_with_issues(
        self, agent: ReviewAgent, ctx: AgentContext
    ):
        """run() should detect issues and reflect them in the report."""
        ctx.translated_md = (
            "# Title\n\n"
            "### Subsection\n\n"  # Broken heading (skips level 2)
            "Transformer 是一种变换器模型。\n"
            "Transformer 也被称为转换器架构。\n\n"  # Inconsistent term
            "This is an untranslated paragraph that spans\n"
            "multiple lines and should be detected by the\n"
            "review agent as needing translation.\n"
        )
        ctx.glossary = {"Transformer": "变换器"}

        result = await agent.run(ctx)
        report = result.quality_report

        assert report is not None
        assert report.score < 100
        # Should have at least one heading issue
        heading_issues = [
            i for i in report.format_issues if i.issue_type == "broken_heading"
        ]
        assert len(heading_issues) >= 1

    @pytest.mark.asyncio
    async def test_run_perfect_score(
        self, agent: ReviewAgent, ctx: AgentContext
    ):
        """run() with clean text should produce score of 100."""
        ctx.translated_md = (
            "# 标题\n\n"
            "## 子标题\n\n"
            "这是一段完整的中文翻译文本。\n"
            "Transformer 是一种变换器模型。\n"
            "attention 机制即注意力机制。\n"
        )
        ctx.glossary = {"Transformer": "变换器", "attention": "注意力"}

        result = await agent.run(ctx)
        assert result.quality_report is not None
        assert result.quality_report.score == 100

    @pytest.mark.asyncio
    async def test_run_empty_text(
        self, agent: ReviewAgent, ctx: AgentContext
    ):
        """run() with empty translated_md should produce score of 100."""
        ctx.translated_md = ""
        result = await agent.run(ctx)
        assert result.quality_report is not None
        assert result.quality_report.score == 100

    @pytest.mark.asyncio
    async def test_run_returns_same_context(
        self, agent: ReviewAgent, ctx: AgentContext
    ):
        """run() should return the same context object."""
        ctx.translated_md = "一些中文文本。\n"
        result = await agent.run(ctx)
        assert result is ctx
