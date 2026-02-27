from __future__ import annotations

import re
from typing import Any

from agent.qa_orchestration.contracts_v1 import WorkerResultV1, WorkerRole, WorkerRunContextV1, WorkerTaskV1

from .base_worker_v1 import BaseWorkerV1


class ResearcherWorkerV1(BaseWorkerV1):
    name = "researcher-worker-v1"
    role = WorkerRole.RESEARCHER
    identity_prompt = "你是 Researcher Worker，负责检索与归纳证据，强调来源与可追溯性，不直接给最终回答。"
    capabilities = {
        "context.retrieve",
        "research.retrieve",
        "research.reflect",
    }

    async def run(self, task: WorkerTaskV1, context: WorkerRunContextV1) -> WorkerResultV1:
        cleaned_evidence: list[tuple[str, dict[str, Any]]] = []
        seen: set[str] = set()
        for item in context.selected_context[:8]:
            raw_summary = str(item.get("summary") or "")
            cleaned = self._clean_context_text(raw_summary)
            if not cleaned:
                continue
            key = self._fingerprint(cleaned)
            if key in seen:
                continue
            seen.add(key)
            cleaned_evidence.append((cleaned, item))
            if len(cleaned_evidence) >= 4:
                break

        if cleaned_evidence:
            evidence_points = [item[0] for item in cleaned_evidence]
            text = "；".join(evidence_points)
            citations = [
                {
                    "source": str(meta.get("turn_id") or "unknown"),
                    "score": float(meta.get("score") or 0.0),
                    "text": point,
                }
                for point, meta in cleaned_evidence
            ]
        else:
            evidence_points = []
            text = "未命中高质量历史证据，建议以当前问题触发外部检索。"
            citations = []

        return WorkerResultV1(
            success=True,
            output={
                "text": text,
                "summary": text,
                "evidence_points": evidence_points,
                "selected_turn_ids": [str(meta.get("turn_id")) for _, meta in cleaned_evidence],
            },
            citations=citations,
        )

    def _clean_context_text(self, text: str) -> str:
        normalized = text.replace("\n", " ").strip()
        if "| A:" in normalized:
            normalized = normalized.split("| A:", 1)[-1].strip()
        normalized = re.sub(r"^Q:\s*", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized[:180]

    def _fingerprint(self, text: str) -> str:
        return re.sub(r"\W+", "", text.lower())[:60]
