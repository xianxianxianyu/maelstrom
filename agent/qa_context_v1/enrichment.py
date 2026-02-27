from __future__ import annotations

import re
from typing import Any


class TurnEnricher:
    def build_summary(self, query: str, answer: str | None) -> str:
        query_part = query.strip().replace("\n", " ")[:64]
        answer_part = (answer or "").strip().replace("\n", " ")[:64]
        if answer_part:
            return f"Q: {query_part} | A: {answer_part}"
        return f"Q: {query_part}"

    def extract_entities(self, query: str, answer: str | None) -> list[dict[str, Any]]:
        text = f"{query} {answer or ''}"
        tokens = set(re.findall(r"[A-Za-z0-9_\-]{3,}", text))
        entities: list[dict[str, Any]] = []
        for value in sorted(tokens)[:12]:
            entities.append({"type": "token", "value": value})
        return entities

    def build_tags(
        self,
        intent_tag: str,
        entities: list[dict[str, Any]],
        referenced_docs: list[str],
        stage2_result: dict[str, Any],
    ) -> tuple[list[str], list[str]]:
        tags = ["qa-v1", intent_tag.lower()]
        if referenced_docs:
            tags.append("doc-grounded")
        if len(stage2_result.get("sub_problems", [])) > 1:
            tags.append("multi-step")
        for item in entities[:4]:
            value = str(item.get("value", "")).lower().strip()
            if value:
                tags.append(value)

        topic_tags = [tag for tag in tags if tag not in {"qa-v1", intent_tag.lower()}]
        dedup_tags = sorted({tag for tag in tags if tag})
        dedup_topics = sorted({tag for tag in topic_tags if tag})
        return dedup_tags, dedup_topics
