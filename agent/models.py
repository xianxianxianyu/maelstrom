"""数据模型 — QualityReport、TermIssue、FormatIssue、GlossaryEntry

提供翻译质量报告和术语管理的核心数据类，支持 JSON 序列化/反序列化
（to_dict/from_dict 方法），用于持久化存储和 API 传输。

Requirements: 2.4, 3.4, 7.2
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TermIssue:
    """术语不一致问题

    当同一英文术语在翻译文本中出现了多种不同的中文翻译时，
    ReviewAgent 会创建此对象记录问题详情。

    Attributes:
        english_term: 英文术语
        translations: 出现的不同翻译列表
        locations: 出现位置（行号或段落标识）
        suggested: 建议统一翻译
    """

    english_term: str
    translations: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    suggested: str = ""

    def to_dict(self) -> dict:
        """序列化为普通字典（JSON 可序列化）"""
        return {
            "english_term": self.english_term,
            "translations": list(self.translations),
            "locations": list(self.locations),
            "suggested": self.suggested,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TermIssue:
        """从字典创建实例

        Args:
            data: 包含 TermIssue 字段的字典

        Returns:
            TermIssue 实例
        """
        return cls(
            english_term=data["english_term"],
            translations=list(data.get("translations", [])),
            locations=list(data.get("locations", [])),
            suggested=data.get("suggested", ""),
        )


@dataclass
class FormatIssue:
    """格式问题

    当翻译文本中存在格式完整性问题时（如表格损坏、公式缺失等），
    ReviewAgent 会创建此对象记录问题详情。

    Attributes:
        issue_type: 问题类型，取值为
            "broken_table" | "missing_formula" | "broken_heading" | "missing_image"
        location: 问题位置（行号或段落标识）
        description: 问题描述
    """

    issue_type: str
    location: str
    description: str

    def to_dict(self) -> dict:
        """序列化为普通字典（JSON 可序列化）"""
        return {
            "issue_type": self.issue_type,
            "location": self.location,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> FormatIssue:
        """从字典创建实例

        Args:
            data: 包含 FormatIssue 字段的字典

        Returns:
            FormatIssue 实例
        """
        return cls(
            issue_type=data["issue_type"],
            location=data["location"],
            description=data["description"],
        )


@dataclass
class QualityReport:
    """翻译质量报告

    ReviewAgent 完成审校后生成此报告，包含总体评分、问题列表和改进建议。
    报告会被持久化为 quality_report.json 存储在 Translation/{id}/ 文件夹中。

    Attributes:
        score: 总体评分（0-100）
        terminology_issues: 术语不一致问题列表
        format_issues: 格式问题列表
        untranslated: 未翻译的英文段落列表
        suggestions: 改进建议列表
        timestamp: ISO 格式时间戳
    """

    score: int
    terminology_issues: list[TermIssue] = field(default_factory=list)
    format_issues: list[FormatIssue] = field(default_factory=list)
    untranslated: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        """序列化为普通字典（JSON 可序列化）

        嵌套的 TermIssue 和 FormatIssue 对象会递归调用各自的 to_dict()。
        """
        return {
            "score": self.score,
            "terminology_issues": [issue.to_dict() for issue in self.terminology_issues],
            "format_issues": [issue.to_dict() for issue in self.format_issues],
            "untranslated": list(self.untranslated),
            "suggestions": list(self.suggestions),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> QualityReport:
        """从字典创建实例

        处理嵌套的 TermIssue 和 FormatIssue 列表，将字典递归转换为对应的数据类实例。

        Args:
            data: 包含 QualityReport 字段的字典

        Returns:
            QualityReport 实例
        """
        return cls(
            score=data["score"],
            terminology_issues=[
                TermIssue.from_dict(item)
                for item in data.get("terminology_issues", [])
            ],
            format_issues=[
                FormatIssue.from_dict(item)
                for item in data.get("format_issues", [])
            ],
            untranslated=list(data.get("untranslated", [])),
            suggestions=list(data.get("suggestions", [])),
            timestamp=data.get("timestamp", ""),
        )


@dataclass
class GlossaryEntry:
    """术语条目

    领域术语表中的单个条目，包含英文术语及其中文翻译、
    是否保留英文、所属领域、来源和更新时间。

    术语表以 JSON 文件形式存储在 Translation/glossaries/{domain}.json。

    Attributes:
        english: 英文术语
        chinese: 中文翻译
        keep_english: 是否在翻译中保留英文原文
        domain: 所属领域（如 "nlp"、"cv"）
        source: 来源（论文名或 "user_edit"）
        updated_at: 最后更新时间（ISO 格式）
    """

    english: str
    chinese: str
    keep_english: bool = False
    domain: str = ""
    source: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        """序列化为普通字典（JSON 可序列化）"""
        return {
            "english": self.english,
            "chinese": self.chinese,
            "keep_english": self.keep_english,
            "domain": self.domain,
            "source": self.source,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> GlossaryEntry:
        """从字典创建实例

        Args:
            data: 包含 GlossaryEntry 字段的字典

        Returns:
            GlossaryEntry 实例
        """
        return cls(
            english=data["english"],
            chinese=data["chinese"],
            keep_english=data.get("keep_english", False),
            domain=data.get("domain", ""),
            source=data.get("source", ""),
            updated_at=data.get("updated_at", ""),
        )
