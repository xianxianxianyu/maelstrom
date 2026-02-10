"""Unit tests for agent/models.py — QualityReport, TermIssue, FormatIssue, GlossaryEntry

Tests cover:
- to_dict() serialization for each dataclass
- from_dict() deserialization for each dataclass
- Round-trip (to_dict → from_dict) equivalence
- Nested object handling in QualityReport
- Default values and edge cases
"""

import json

import pytest

from agent.models import FormatIssue, GlossaryEntry, QualityReport, TermIssue


# ---------------------------------------------------------------------------
# TermIssue
# ---------------------------------------------------------------------------

class TestTermIssue:
    """Tests for TermIssue dataclass."""

    def test_to_dict(self):
        issue = TermIssue(
            english_term="attention mechanism",
            translations=["注意力机制", "注意机制"],
            locations=["line 5", "line 20"],
            suggested="注意力机制",
        )
        result = issue.to_dict()
        assert result == {
            "english_term": "attention mechanism",
            "translations": ["注意力机制", "注意机制"],
            "locations": ["line 5", "line 20"],
            "suggested": "注意力机制",
        }

    def test_from_dict(self):
        data = {
            "english_term": "Transformer",
            "translations": ["Transformer 模型", "变换器"],
            "locations": ["paragraph 1"],
            "suggested": "Transformer",
        }
        issue = TermIssue.from_dict(data)
        assert issue.english_term == "Transformer"
        assert issue.translations == ["Transformer 模型", "变换器"]
        assert issue.locations == ["paragraph 1"]
        assert issue.suggested == "Transformer"

    def test_from_dict_with_defaults(self):
        data = {"english_term": "BERT"}
        issue = TermIssue.from_dict(data)
        assert issue.english_term == "BERT"
        assert issue.translations == []
        assert issue.locations == []
        assert issue.suggested == ""

    def test_round_trip(self):
        original = TermIssue(
            english_term="fine-tuning",
            translations=["微调", "精调"],
            locations=["line 10", "line 42"],
            suggested="微调",
        )
        restored = TermIssue.from_dict(original.to_dict())
        assert restored == original

    def test_json_serializable(self):
        issue = TermIssue(
            english_term="embedding",
            translations=["嵌入"],
            locations=["line 3"],
            suggested="嵌入",
        )
        json_str = json.dumps(issue.to_dict(), ensure_ascii=False)
        restored = TermIssue.from_dict(json.loads(json_str))
        assert restored == issue


# ---------------------------------------------------------------------------
# FormatIssue
# ---------------------------------------------------------------------------

class TestFormatIssue:
    """Tests for FormatIssue dataclass."""

    def test_to_dict(self):
        issue = FormatIssue(
            issue_type="broken_table",
            location="line 15",
            description="表格第3行缺少分隔符",
        )
        result = issue.to_dict()
        assert result == {
            "issue_type": "broken_table",
            "location": "line 15",
            "description": "表格第3行缺少分隔符",
        }

    def test_from_dict(self):
        data = {
            "issue_type": "missing_formula",
            "location": "paragraph 5",
            "description": "公式未闭合",
        }
        issue = FormatIssue.from_dict(data)
        assert issue.issue_type == "missing_formula"
        assert issue.location == "paragraph 5"
        assert issue.description == "公式未闭合"

    def test_round_trip(self):
        original = FormatIssue(
            issue_type="broken_heading",
            location="line 1",
            description="标题层级跳跃：从 H1 直接到 H3",
        )
        restored = FormatIssue.from_dict(original.to_dict())
        assert restored == original

    def test_all_issue_types(self):
        """Verify all defined issue types can be represented."""
        for issue_type in ("broken_table", "missing_formula", "broken_heading", "missing_image"):
            issue = FormatIssue(issue_type=issue_type, location="loc", description="desc")
            restored = FormatIssue.from_dict(issue.to_dict())
            assert restored.issue_type == issue_type


# ---------------------------------------------------------------------------
# QualityReport
# ---------------------------------------------------------------------------

class TestQualityReport:
    """Tests for QualityReport dataclass."""

    def test_to_dict_with_nested_objects(self):
        report = QualityReport(
            score=85,
            terminology_issues=[
                TermIssue(
                    english_term="loss function",
                    translations=["损失函数", "代价函数"],
                    locations=["line 5", "line 30"],
                    suggested="损失函数",
                ),
            ],
            format_issues=[
                FormatIssue(
                    issue_type="broken_table",
                    location="line 20",
                    description="表格结构不完整",
                ),
            ],
            untranslated=["This paragraph was not translated."],
            suggestions=["统一 loss function 的翻译为「损失函数」"],
            timestamp="2024-01-15T10:30:00",
        )
        result = report.to_dict()

        assert result["score"] == 85
        assert len(result["terminology_issues"]) == 1
        assert result["terminology_issues"][0]["english_term"] == "loss function"
        assert len(result["format_issues"]) == 1
        assert result["format_issues"][0]["issue_type"] == "broken_table"
        assert result["untranslated"] == ["This paragraph was not translated."]
        assert len(result["suggestions"]) == 1
        assert result["timestamp"] == "2024-01-15T10:30:00"

    def test_from_dict_with_nested_objects(self):
        data = {
            "score": 72,
            "terminology_issues": [
                {
                    "english_term": "gradient descent",
                    "translations": ["梯度下降", "梯度递减"],
                    "locations": ["line 8"],
                    "suggested": "梯度下降",
                }
            ],
            "format_issues": [
                {
                    "issue_type": "missing_image",
                    "location": "line 50",
                    "description": "图片引用丢失",
                }
            ],
            "untranslated": [],
            "suggestions": ["建议统一术语翻译"],
            "timestamp": "2024-06-01T12:00:00",
        }
        report = QualityReport.from_dict(data)

        assert report.score == 72
        assert len(report.terminology_issues) == 1
        assert isinstance(report.terminology_issues[0], TermIssue)
        assert report.terminology_issues[0].english_term == "gradient descent"
        assert len(report.format_issues) == 1
        assert isinstance(report.format_issues[0], FormatIssue)
        assert report.format_issues[0].issue_type == "missing_image"
        assert report.untranslated == []
        assert report.suggestions == ["建议统一术语翻译"]
        assert report.timestamp == "2024-06-01T12:00:00"

    def test_from_dict_with_defaults(self):
        data = {"score": 50}
        report = QualityReport.from_dict(data)
        assert report.score == 50
        assert report.terminology_issues == []
        assert report.format_issues == []
        assert report.untranslated == []
        assert report.suggestions == []
        assert report.timestamp == ""

    def test_round_trip(self):
        original = QualityReport(
            score=90,
            terminology_issues=[
                TermIssue("NLP", ["自然语言处理", "NLP"], ["line 1"], "自然语言处理"),
                TermIssue("CNN", ["卷积神经网络"], ["line 10"], "卷积神经网络"),
            ],
            format_issues=[
                FormatIssue("broken_table", "line 25", "表格列数不一致"),
                FormatIssue("missing_formula", "line 40", "公式定界符未闭合"),
            ],
            untranslated=["Abstract paragraph 1", "Conclusion paragraph 3"],
            suggestions=["统一 NLP 翻译", "修复表格格式"],
            timestamp="2024-03-20T08:15:00",
        )
        restored = QualityReport.from_dict(original.to_dict())
        assert restored == original

    def test_json_serializable(self):
        report = QualityReport(
            score=75,
            terminology_issues=[
                TermIssue("token", ["令牌", "标记"], ["line 2"], "令牌"),
            ],
            format_issues=[],
            untranslated=["Some English text"],
            suggestions=["Fix terminology"],
            timestamp="2024-01-01T00:00:00",
        )
        json_str = json.dumps(report.to_dict(), ensure_ascii=False)
        restored = QualityReport.from_dict(json.loads(json_str))
        assert restored == report

    def test_empty_report(self):
        report = QualityReport(score=100, timestamp="2024-01-01T00:00:00")
        result = report.to_dict()
        assert result["terminology_issues"] == []
        assert result["format_issues"] == []
        assert result["untranslated"] == []
        assert result["suggestions"] == []

        restored = QualityReport.from_dict(result)
        assert restored == report


# ---------------------------------------------------------------------------
# GlossaryEntry
# ---------------------------------------------------------------------------

class TestGlossaryEntry:
    """Tests for GlossaryEntry dataclass."""

    def test_to_dict(self):
        entry = GlossaryEntry(
            english="Transformer",
            chinese="Transformer",
            keep_english=True,
            domain="nlp",
            source="Attention Is All You Need",
            updated_at="2024-01-01T00:00:00",
        )
        result = entry.to_dict()
        assert result == {
            "english": "Transformer",
            "chinese": "Transformer",
            "keep_english": True,
            "domain": "nlp",
            "source": "Attention Is All You Need",
            "updated_at": "2024-01-01T00:00:00",
        }

    def test_from_dict(self):
        data = {
            "english": "attention mechanism",
            "chinese": "注意力机制",
            "keep_english": False,
            "domain": "nlp",
            "source": "user_edit",
            "updated_at": "2024-06-15T09:00:00",
        }
        entry = GlossaryEntry.from_dict(data)
        assert entry.english == "attention mechanism"
        assert entry.chinese == "注意力机制"
        assert entry.keep_english is False
        assert entry.domain == "nlp"
        assert entry.source == "user_edit"
        assert entry.updated_at == "2024-06-15T09:00:00"

    def test_from_dict_with_defaults(self):
        data = {"english": "BERT", "chinese": "BERT"}
        entry = GlossaryEntry.from_dict(data)
        assert entry.english == "BERT"
        assert entry.chinese == "BERT"
        assert entry.keep_english is False
        assert entry.domain == ""
        assert entry.source == ""
        assert entry.updated_at == ""

    def test_round_trip(self):
        original = GlossaryEntry(
            english="convolutional neural network",
            chinese="卷积神经网络",
            keep_english=False,
            domain="cv",
            source="ImageNet paper",
            updated_at="2024-02-10T14:30:00",
        )
        restored = GlossaryEntry.from_dict(original.to_dict())
        assert restored == original

    def test_json_serializable(self):
        entry = GlossaryEntry(
            english="backpropagation",
            chinese="反向传播",
            keep_english=False,
            domain="ml",
            source="user_edit",
            updated_at="2024-05-01T00:00:00",
        )
        json_str = json.dumps(entry.to_dict(), ensure_ascii=False)
        restored = GlossaryEntry.from_dict(json.loads(json_str))
        assert restored == entry

    def test_keep_english_true(self):
        entry = GlossaryEntry(
            english="LSTM",
            chinese="LSTM",
            keep_english=True,
            domain="nlp",
            source="paper.pdf",
            updated_at="2024-01-01T00:00:00",
        )
        d = entry.to_dict()
        assert d["keep_english"] is True
        restored = GlossaryEntry.from_dict(d)
        assert restored.keep_english is True
