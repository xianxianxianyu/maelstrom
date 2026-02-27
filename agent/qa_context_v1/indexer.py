from __future__ import annotations

from typing import Any

from .models import DialogueTurn
from .store import SessionSQLiteStore


class QAContextIndexer:
    def __init__(self, store: SessionSQLiteStore) -> None:
        self.store = store

    def select_context(
        self,
        session_id: str,
        query: str,
        intent_hint: str | None = None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        candidates = self.store.search_turns(
            session_id=session_id,
            query=query,
            intent_tag=intent_hint if intent_hint and intent_hint != "UNKNOWN" else None,
            limit=max(limit * 3, limit),
        )
        ranked = self._rank(query, candidates)
        return ranked[:limit]

    def _rank(self, query: str, turns: list[DialogueTurn]) -> list[dict[str, Any]]:
        query_tokens = self._tokens(query)
        total = max(len(turns), 1)
        ranked: list[dict[str, Any]] = []
        for index, turn in enumerate(turns):
            recency = 1.0 - (index / total)
            body = " ".join([turn.user_query, turn.summary, turn.assistant_answer or ""])
            body_tokens = self._tokens(body)
            overlap = len(query_tokens.intersection(body_tokens)) / max(len(query_tokens), 1)
            score = round((0.65 * overlap) + (0.35 * recency), 4)
            ranked.append(
                {
                    "turn_id": turn.turn_id,
                    "summary": turn.summary,
                    "intent_tag": turn.intent_tag,
                    "tags": turn.tags,
                    "score": score,
                }
            )
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked

    def _tokens(self, text: str) -> set[str]:
        return {token.strip().lower() for token in text.split() if token.strip()}
