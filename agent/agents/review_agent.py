"""ReviewAgent — 翻译质量审校 Agent

检查术语一致性、格式完整性、未翻译段落检测，生成 QualityReport。

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from agent.base import BaseAgent
from agent.context import AgentContext
from agent.models import FormatIssue, QualityReport, TermIssue
from agent.registry import agent_registry

logger = logging.getLogger(__name__)


@agent_registry.register
class ReviewAgent(BaseAgent):
    """审校 Agent：检查术语一致性、格式完整性、生成质量报告

    Workflow:
        1. _check_terminology_consistency: 检测同一术语的不同翻译
        2. _check_format_integrity: 检查表格、公式、标题完整性
        3. _detect_untranslated: 检测未翻译的英文段落
        4. _build_quality_report: 汇总生成 QualityReport（0-100 评分）
    """

    @property
    def name(self) -> str:
        return "review"

    @property
    def description(self) -> str:
        return "审校 Agent：检查术语一致性、格式完整性、生成质量报告"

    async def run(self, input_data: AgentContext, **kwargs) -> AgentContext:
        """执行审校 Agent 主逻辑

        Args:
            input_data: AgentContext 共享上下文（需要 translated_md 和 glossary）

        Returns:
            更新后的 AgentContext（quality_report 已填充）
        """
        ctx = input_data

        # 1. 术语一致性检查
        term_issues = self._check_terminology_consistency(
            ctx.translated_md, ctx.glossary
        )

        # 2. 格式完整性检查
        format_issues = self._check_format_integrity(ctx.translated_md)

        # 3. 未翻译段落检测
        untranslated = self._detect_untranslated(ctx.translated_md)

        # 4. 生成质量报告
        report = self._build_quality_report(term_issues, format_issues, untranslated)
        ctx.quality_report = report

        logger.info(
            "Review complete: score=%d, term_issues=%d, format_issues=%d, untranslated=%d",
            report.score,
            len(report.terminology_issues),
            len(report.format_issues),
            len(report.untranslated),
        )

        return ctx

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _check_terminology_consistency(
        self, translated_md: str, glossary: dict[str, str]
    ) -> list[TermIssue]:
        """检测同一术语的不同翻译

        For each English term in the glossary, search the translated text for
        the expected Chinese translation and any other Chinese text that appears
        near the English term. If a term has multiple different translations,
        create a TermIssue.

        Args:
            translated_md: 翻译后的 Markdown 文本
            glossary: 术语表 {英文术语: 中文翻译}

        Returns:
            术语不一致问题列表
        """
        if not translated_md or not glossary:
            return []

        issues: list[TermIssue] = []
        lines = translated_md.split("\n")

        for english_term, expected_chinese in glossary.items():
            # Find all lines containing the English term (case-insensitive)
            pattern = re.compile(re.escape(english_term), re.IGNORECASE)
            found_translations: dict[str, list[str]] = {}

            for line_num, line in enumerate(lines, start=1):
                if pattern.search(line):
                    # Look for Chinese text near the English term in this line
                    # Extract Chinese segments from the line
                    chinese_segments = re.findall(
                        r"[\u4e00-\u9fff]+", line
                    )
                    location = f"Line {line_num}"

                    # Check if the expected translation appears in this line
                    if expected_chinese and expected_chinese in line:
                        found_translations.setdefault(expected_chinese, []).append(
                            location
                        )
                    else:
                        # The English term appears but the expected translation
                        # is not on this line — record any Chinese near it
                        for seg in chinese_segments:
                            if len(seg) >= 2:  # Skip single-char noise
                                found_translations.setdefault(seg, []).append(
                                    location
                                )

            # Also check for lines that contain the expected Chinese translation
            # but NOT the English term — these are consistent usages
            if expected_chinese:
                for line_num, line in enumerate(lines, start=1):
                    if expected_chinese in line and not pattern.search(line):
                        found_translations.setdefault(expected_chinese, []).append(
                            f"Line {line_num}"
                        )

            # If we found multiple different translations, report an issue
            if len(found_translations) > 1:
                all_locations: list[str] = []
                for locs in found_translations.values():
                    all_locations.extend(locs)

                issues.append(
                    TermIssue(
                        english_term=english_term,
                        translations=list(found_translations.keys()),
                        locations=sorted(set(all_locations)),
                        suggested=expected_chinese,
                    )
                )

        return issues

    def _check_format_integrity(self, translated_md: str) -> list[FormatIssue]:
        """检查表格、公式、标题完整性

        Checks:
        - Broken tables: rows with inconsistent column counts
        - Unclosed math delimiters: unmatched $ or $$
        - Broken headings: heading level jumps (e.g., # → ### skipping ##)
        - Missing images: ![alt](path) where path looks invalid

        Args:
            translated_md: 翻译后的 Markdown 文本

        Returns:
            格式问题列表
        """
        if not translated_md:
            return []

        issues: list[FormatIssue] = []
        lines = translated_md.split("\n")

        # --- Check broken tables ---
        issues.extend(self._check_broken_tables(lines))

        # --- Check unclosed math delimiters ---
        issues.extend(self._check_unclosed_math(translated_md, lines))

        # --- Check broken headings ---
        issues.extend(self._check_broken_headings(lines))

        # --- Check missing images ---
        issues.extend(self._check_missing_images(lines))

        return issues

    def _check_broken_tables(self, lines: list[str]) -> list[FormatIssue]:
        """Check for tables with inconsistent column counts."""
        issues: list[FormatIssue] = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # Detect table start: line starts with | and has at least 2 |
            if line.startswith("|") and line.count("|") >= 2:
                table_start = i + 1  # 1-indexed
                table_lines: list[tuple[int, str]] = []

                # Collect all consecutive table lines
                while i < len(lines) and lines[i].strip().startswith("|"):
                    table_lines.append((i + 1, lines[i].strip()))
                    i += 1

                # Check column consistency (skip separator rows)
                col_counts: list[int] = []
                for line_num, tline in table_lines:
                    # Count columns: split by | and filter empty
                    cols = [
                        c for c in tline.split("|") if c.strip() != ""
                    ]
                    # Skip separator rows (all dashes/colons)
                    if all(
                        re.match(r"^[\s\-:]+$", c) for c in cols
                    ):
                        col_counts.append(len(cols))
                        continue
                    col_counts.append(len(cols))

                if col_counts and len(set(col_counts)) > 1:
                    issues.append(
                        FormatIssue(
                            issue_type="broken_table",
                            location=f"Line {table_start}",
                            description=(
                                f"Table has inconsistent column counts: "
                                f"{sorted(set(col_counts))}"
                            ),
                        )
                    )
            else:
                i += 1

        return issues

    def _check_unclosed_math(
        self, text: str, lines: list[str]
    ) -> list[FormatIssue]:
        """Check for unclosed math delimiters ($ or $$)."""
        issues: list[FormatIssue] = []

        # Check display math $$...$$
        # Count $$ occurrences (must be even)
        display_delimiters = re.findall(r"\$\$", text)
        if len(display_delimiters) % 2 != 0:
            # Find the location of the unmatched $$
            for line_num, line in enumerate(lines, start=1):
                if "$$" in line:
                    issues.append(
                        FormatIssue(
                            issue_type="missing_formula",
                            location=f"Line {line_num}",
                            description="Unmatched display math delimiter ($$)",
                        )
                    )
                    break

        # Check inline math $...$
        # Remove display math first to avoid false positives
        text_no_display = re.sub(r"\$\$.*?\$\$", "", text, flags=re.DOTALL)
        # Remove code blocks to avoid false positives
        text_no_code = re.sub(r"```.*?```", "", text_no_display, flags=re.DOTALL)
        text_no_inline_code = re.sub(r"`[^`]+`", "", text_no_code)

        inline_dollars = re.findall(r"\$", text_no_inline_code)
        if len(inline_dollars) % 2 != 0:
            # Find the location
            for line_num, line in enumerate(lines, start=1):
                # Skip lines with $$ (display math)
                line_no_display = re.sub(r"\$\$", "", line)
                line_no_code = re.sub(r"`[^`]+`", "", line_no_display)
                dollar_count = line_no_code.count("$")
                if dollar_count % 2 != 0:
                    issues.append(
                        FormatIssue(
                            issue_type="missing_formula",
                            location=f"Line {line_num}",
                            description="Unmatched inline math delimiter ($)",
                        )
                    )
                    break

        return issues

    def _check_broken_headings(self, lines: list[str]) -> list[FormatIssue]:
        """Check for heading level jumps (e.g., # → ### skipping ##)."""
        issues: list[FormatIssue] = []
        last_level = 0

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()
            # Match markdown headings: # Title, ## Title, etc.
            match = re.match(r"^(#{1,6})\s+\S", stripped)
            if match:
                level = len(match.group(1))
                if last_level > 0 and level > last_level + 1:
                    issues.append(
                        FormatIssue(
                            issue_type="broken_heading",
                            location=f"Line {line_num}",
                            description=(
                                f"Heading level jumps from {last_level} to {level} "
                                f"(skipped level {last_level + 1})"
                            ),
                        )
                    )
                last_level = level

        return issues

    def _check_missing_images(self, lines: list[str]) -> list[FormatIssue]:
        """Check for image references with invalid-looking paths."""
        issues: list[FormatIssue] = []
        image_pattern = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")

        for line_num, line in enumerate(lines, start=1):
            for match in image_pattern.finditer(line):
                alt_text = match.group(1)
                path = match.group(2).strip()

                # Check for empty or obviously invalid paths
                if not path or path.isspace():
                    issues.append(
                        FormatIssue(
                            issue_type="missing_image",
                            location=f"Line {line_num}",
                            description=f"Image reference has empty path: ![{alt_text}]()",
                        )
                    )

        return issues

    def _detect_untranslated(self, translated_md: str) -> list[str]:
        """检测未翻译的英文段落

        Find paragraphs that are purely English (3+ consecutive lines without
        Chinese characters), excluding:
        - Code blocks (``` ... ```)
        - LaTeX blocks ($$ ... $$)
        - Lines that look like proper nouns or technical terms (short lines)

        Args:
            translated_md: 翻译后的 Markdown 文本

        Returns:
            未翻译的英文段落文本列表
        """
        if not translated_md:
            return []

        lines = translated_md.split("\n")
        untranslated: list[str] = []

        # First, identify regions to exclude (code blocks and LaTeX blocks)
        excluded_lines: set[int] = set()

        # Exclude code blocks
        in_code_block = False
        for i, line in enumerate(lines):
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                excluded_lines.add(i)
            elif in_code_block:
                excluded_lines.add(i)

        # Exclude display LaTeX blocks ($$...$$)
        in_latex_block = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "$$":
                in_latex_block = not in_latex_block
                excluded_lines.add(i)
            elif in_latex_block:
                excluded_lines.add(i)

        # Now scan for consecutive English-only lines
        has_chinese = re.compile(r"[\u4e00-\u9fff]")
        consecutive_english: list[tuple[int, str]] = []

        def _flush_english_block() -> None:
            """Check and flush the current block of English lines."""
            if len(consecutive_english) >= 3:
                block_text = "\n".join(text for _, text in consecutive_english)
                untranslated.append(block_text)
            consecutive_english.clear()

        for i, line in enumerate(lines):
            if i in excluded_lines:
                _flush_english_block()
                continue

            stripped = line.strip()

            # Skip empty lines — they break paragraphs
            if not stripped:
                _flush_english_block()
                continue

            # Skip heading lines (they may be short English)
            if stripped.startswith("#"):
                _flush_english_block()
                continue

            # Skip short lines (likely proper nouns, labels, etc.)
            # A "short line" is <= 30 characters with no spaces (single term)
            if len(stripped) <= 30 and " " not in stripped:
                _flush_english_block()
                continue

            # Check if line contains Chinese characters
            if has_chinese.search(stripped):
                _flush_english_block()
            else:
                # Check if line has meaningful English content
                # (not just punctuation, numbers, or whitespace)
                if re.search(r"[a-zA-Z]{2,}", stripped):
                    consecutive_english.append((i, stripped))
                else:
                    _flush_english_block()

        # Flush any remaining block
        _flush_english_block()

        return untranslated

    def _build_quality_report(
        self,
        term_issues: list[TermIssue],
        format_issues: list[FormatIssue],
        untranslated: list[str],
    ) -> QualityReport:
        """汇总生成 QualityReport（0-100 评分）

        Scoring:
        - Start with score = 100
        - Deduct 5 points per terminology issue
        - Deduct 3 points per format issue
        - Deduct 2 points per untranslated paragraph
        - Clamp score to [0, 100]

        Args:
            term_issues: 术语不一致问题列表
            format_issues: 格式问题列表
            untranslated: 未翻译段落列表

        Returns:
            QualityReport 实例
        """
        score = 100
        score -= 5 * len(term_issues)
        score -= 3 * len(format_issues)
        score -= 2 * len(untranslated)
        score = max(0, min(100, score))

        suggestions: list[str] = []

        if term_issues:
            suggestions.append(
                f"发现 {len(term_issues)} 个术语不一致问题，"
                f"建议统一术语翻译以提高一致性。"
            )
            for issue in term_issues:
                suggestions.append(
                    f"术语 '{issue.english_term}' 建议统一翻译为 "
                    f"'{issue.suggested}'。"
                )

        if format_issues:
            suggestions.append(
                f"发现 {len(format_issues)} 个格式问题，"
                f"请检查表格、公式和标题的完整性。"
            )

        if untranslated:
            suggestions.append(
                f"发现 {len(untranslated)} 个未翻译的英文段落，"
                f"建议补充翻译。"
            )

        timestamp = datetime.now(timezone.utc).isoformat()

        return QualityReport(
            score=score,
            terminology_issues=term_issues,
            format_issues=format_issues,
            untranslated=untranslated,
            suggestions=suggestions,
            timestamp=timestamp,
        )
