from __future__ import annotations

import re

from agent.qa_orchestration.contracts_v1 import WorkerResultV1, WorkerRole, WorkerRunContextV1, WorkerTaskV1

from .base_worker_v1 import BaseWorkerV1


class VerifierWorkerV1(BaseWorkerV1):
    name = "verifier-worker-v1"
    role = WorkerRole.VERIFIER
    identity_prompt = "你是 Verifier Worker，负责校验证据与答案一致性；不通过时明确失败原因并阻断结果。"
    capabilities = {"grounding.verify"}

    async def run(self, task: WorkerTaskV1, context: WorkerRunContextV1) -> WorkerResultV1:
        route = str(task.payload.get("route_type") or "")
        answer = str(task.payload.get("answer") or "")
        citations = list(task.payload.get("citations") or [])
        evidence_items = list(task.payload.get("evidence_items") or [])

        reasons: list[str] = []
        if route not in {"fast_path", "chat"} and not citations:
            reasons.append("grounded path requires citations")

        if route not in {"fast_path", "chat"}:
            if any(not str(citation.get("text") or "").strip() for citation in citations):
                reasons.append("citation text is required for grounded route")

        evidence_texts = [str(item.get("text") or item.get("summary") or "") for item in evidence_items]
        matched = 0
        for citation in citations:
            snippet = str(citation.get("text") or "")[:40]
            if snippet and not any(snippet in text for text in evidence_texts):
                reasons.append("citation not found in evidence")
                break
            if snippet:
                matched += 1

        if route not in {"fast_path", "chat"} and citations and matched == 0:
            reasons.append("no citation-evidence alignment")

        if not answer.strip():
            reasons.append("empty answer")

        if self._has_echo_noise(answer):
            reasons.append("echo noise detected in answer")

        passed = len(reasons) == 0
        return WorkerResultV1(
            success=passed,
            output={
                "passed": passed,
                "reasons": reasons,
                "answer": answer if passed else "",
                "citations": citations if passed else [],
            },
            citations=citations if passed else [],
            error="; ".join(reasons) if reasons else None,
            recoverable=True,
        )

    def _has_echo_noise(self, answer: str) -> bool:
        text = answer.strip()
        if not text:
            return False
        if text.count("Q:") >= 2 or text.count("| A:") >= 2:
            return True
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) < 3:
            return False
        fingerprints = [re.sub(r"\W+", "", line.lower())[:80] for line in lines]
        unique = len(set(fingerprints))
        return unique / max(1, len(fingerprints)) < 0.6
