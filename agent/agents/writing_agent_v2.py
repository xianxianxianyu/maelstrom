from __future__ import annotations

from typing import Dict, List

from agent.core.types import Citation, EvidencePack, RouteType


class WritingAgentV2:
    async def compose_answer(self, query: str, route: RouteType, evidence: EvidencePack) -> Dict[str, object]:
        chunks = evidence.chunks
        if route == RouteType.FAST_PATH:
            answer = f"这是对问题“{query}”的快速回答。"
            return {"answer": answer, "citations": [], "confidence": 0.7}

        if not chunks:
            answer = "当前未检索到可用证据，请补充更具体的问题或文档范围。"
            return {"answer": answer, "citations": [], "confidence": 0.3}

        top_chunks = chunks[:3]
        citations: List[Citation] = []
        snippets: List[str] = []
        for idx, chunk in enumerate(top_chunks, start=1):
            chunk_id = str(chunk.get("source") or f"chunk_{idx}")
            text = str(chunk.get("text") or "")
            score = float(chunk.get("score") or 0.0)
            citations.append(Citation(chunk_id=chunk_id, text=text[:200], score=score))
            if text:
                snippets.append(f"证据{idx}：{text[:120]}")

        answer = "\n".join(
            [
                f"基于检索证据，对问题“{query}”的回答如下：",
                *snippets,
            ]
        )
        confidence = min(0.95, 0.55 + 0.1 * len(citations))
        return {"answer": answer, "citations": citations, "confidence": confidence}
