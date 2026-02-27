from __future__ import annotations

import uuid

from .models import ClarificationThread, Stage2Result, utc_now_iso


class ClarificationManager:
    def should_clarify(self, stage2: Stage2Result) -> bool:
        return stage2.clarification_needed

    def create_thread(self, session_id: str, turn_id: str, query: str, stage2: Stage2Result) -> ClarificationThread:
        now = utc_now_iso()
        return ClarificationThread(
            thread_id=f"clar_{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            turn_id=turn_id,
            created_at=now,
            updated_at=now,
            original_query=query,
            question=stage2.clarification_question or "请补充你的具体目标",
            options=stage2.clarification_options,
            ambiguity_points=["query_scope"],
            status="pending",
        )

    def merge_clarification(self, original_query: str, clarification_answer: str) -> str:
        merged = f"{original_query.strip()}\n补充信息: {clarification_answer.strip()}"
        return merged.strip()
