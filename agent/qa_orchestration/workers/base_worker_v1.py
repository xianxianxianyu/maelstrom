from __future__ import annotations

from agent.qa_orchestration.contracts_v1 import WorkerResultV1, WorkerRunContextV1, WorkerTaskV1


class BaseWorkerV1:
    name = "base-worker-v1"
    capabilities: set[str] = set()

    async def run(self, task: WorkerTaskV1, context: WorkerRunContextV1) -> WorkerResultV1:
        raise NotImplementedError
