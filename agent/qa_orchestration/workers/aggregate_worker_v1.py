from __future__ import annotations

from agent.qa_orchestration.contracts_v1 import WorkerResultV1, WorkerRole, WorkerRunContextV1, WorkerTaskV1

from .base_worker_v1 import BaseWorkerV1


class AggregateWorkerV1(BaseWorkerV1):
    name = "aggregate-worker-v1"
    role = WorkerRole.AGGREGATOR
    identity_prompt = "你是 Aggregate Worker，负责聚合多Worker产物，保留关键信息并合并引用。"
    capabilities = {"aggregate.merge"}

    async def run(self, task: WorkerTaskV1, context: WorkerRunContextV1) -> WorkerResultV1:
        pieces: list[str] = []
        merged_citations: list[dict[str, object]] = []

        for dep_output in task.dependencies.values():
            if not isinstance(dep_output, dict):
                continue
            text = dep_output.get("answer") or dep_output.get("summary") or dep_output.get("text")
            if text:
                pieces.append(str(text))
            dep_citations = dep_output.get("citations")
            if isinstance(dep_citations, list):
                merged_citations.extend(dep_citations)

        summary = "\n".join(pieces).strip() or "暂无可聚合内容"
        return WorkerResultV1(
            success=True,
            output={"summary": summary, "citations": merged_citations},
            citations=merged_citations,
        )
