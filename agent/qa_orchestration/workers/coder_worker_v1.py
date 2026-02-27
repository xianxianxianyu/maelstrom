from __future__ import annotations

import re

from agent.qa_orchestration.contracts_v1 import WorkerResultV1, WorkerRole, WorkerRunContextV1, WorkerTaskV1

from .base_worker_v1 import BaseWorkerV1


class CoderWorkerV1(BaseWorkerV1):
    name = "coder-worker-v1"
    role = WorkerRole.CODER
    identity_prompt = "你是 Coder Worker，负责将上游证据与推理结果转化为清晰答案与结构化输出。"
    capabilities = {
        "reasoning.synthesize",
        "response.compose",
        "code.analyze",
        "code.summarize",
    }

    async def run(self, task: WorkerTaskV1, context: WorkerRunContextV1) -> WorkerResultV1:
        fragments: list[str] = []
        merged_citations: list[dict[str, object]] = []
        seen_fragments: set[str] = set()
        for dep_id, dep_output in task.dependencies.items():
            if not isinstance(dep_output, dict):
                continue
            text = dep_output.get("answer") or dep_output.get("summary") or dep_output.get("text")
            if text:
                cleaned = self._clean_fragment(str(text))
                if cleaned:
                    key = self._fingerprint(cleaned)
                    if key not in seen_fragments:
                        seen_fragments.add(key)
                        fragments.append(cleaned)
            dep_citations = dep_output.get("citations")
            if isinstance(dep_citations, list):
                merged_citations.extend(dep_citations)

        merged_citations = self._dedup_citations(merged_citations)

        if task.capability == "response.compose":
            if fragments:
                answer = self._compose_structured_answer(task.query, fragments)
            else:
                answer = f"已记录问题：{task.query}。当前可用上下文不足，将按新问题处理。"
            return WorkerResultV1(
                success=True,
                output={"answer": answer, "citations": merged_citations},
                citations=merged_citations,
            )

        summary = "\n".join(fragments).strip() or "暂无依赖结果，进入下一步处理。"
        return WorkerResultV1(success=True, output={"summary": summary})

    def _compose_structured_answer(self, query: str, fragments: list[str]) -> str:
        top_points = fragments[:4]
        lines = [
            f"问题：{query}",
            "建议：",
        ]

        if self._is_system_design_query(query):
            lines.extend(
                [
                    "1. 先做短期记忆（当前会话窗口）去重与压缩，避免重复回声。",
                    "2. 长期记忆只存稳定事实与验证通过的结论，不存整段Q/A。",
                    "3. 检索时先语义召回，再做近重复惩罚与证据重排。",
                    "4. 输出前强制验证证据覆盖率与引用完整性。",
                    "关键依据：",
                ]
            )

        for idx, item in enumerate(top_points, start=1):
            lines.append(f"- 依据{idx}：{item}")

        return "\n".join(lines)

    def _clean_fragment(self, text: str) -> str:
        normalized = text.replace("\n", " ").strip()
        normalized = re.sub(r"\[[^\]]+\]\s*", "", normalized)
        if "| A:" in normalized:
            normalized = normalized.split("| A:", 1)[-1].strip()
        normalized = re.sub(r"^Q:\s*", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized[:220]

    def _fingerprint(self, text: str) -> str:
        return re.sub(r"\W+", "", text.lower())[:80]

    def _dedup_citations(self, citations: list[dict[str, object]]) -> list[dict[str, object]]:
        deduped: list[dict[str, object]] = []
        seen: set[str] = set()
        for citation in citations:
            source = str(citation.get("source") or "")
            text = str(citation.get("text") or "")
            key = f"{source}:{self._fingerprint(text)}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(citation)
        return deduped

    def _is_system_design_query(self, query: str) -> bool:
        keys = ["系统", "如何运行", "怎么运行", "架构", "记忆", "上下文"]
        return any(key in query for key in keys)
