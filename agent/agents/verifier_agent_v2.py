from __future__ import annotations

from typing import Dict, List

from agent.core.types import Citation, EvidencePack, RouteType


class VerifierAgentV2:
    async def verify(
        self,
        route: RouteType,
        answer: str,
        citations: List[Citation],
        evidence: EvidencePack,
    ) -> Dict[str, object]:
        reasons: List[str] = []

        if route != RouteType.FAST_PATH and not citations:
            reasons.append("missing citation on grounded route")

        evidence_texts = [str(item.get("text") or "") for item in evidence.chunks]
        for citation in citations:
            if citation.text and not any(citation.text[:40] in text for text in evidence_texts):
                reasons.append(f"citation {citation.chunk_id} 未在证据集中命中")

        if not answer.strip():
            reasons.append("answer 为空")

        passed = len(reasons) == 0
        normalized_answer = answer.strip() if passed else ""

        return {
            "passed": passed,
            "reasons": reasons,
            "answer": normalized_answer,
            "citations": citations if passed else [],
        }
