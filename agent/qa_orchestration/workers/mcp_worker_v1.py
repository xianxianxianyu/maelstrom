from __future__ import annotations

from agent.qa_orchestration.contracts_v1 import WorkerResultV1, WorkerRole, WorkerRunContextV1, WorkerTaskV1

from .base_worker_v1 import BaseWorkerV1


class MCPWorkerV1(BaseWorkerV1):
    name = "mcp-worker-v1"
    role = WorkerRole.MCP
    identity_prompt = "你是 MCP Worker，负责调用工具接口并返回结构化结果，不做主观推理，不产出最终结论。"
    capabilities = {
        "tool.mcp.execute",
        "tool.mcp.read",
        "tool.mcp.fetch",
    }

    async def run(self, task: WorkerTaskV1, context: WorkerRunContextV1) -> WorkerResultV1:
        tool_name = str(task.payload.get("tool") or "mcp.default")
        output = {
            "tool": tool_name,
            "note": "MCP adapter placeholder: no external side effect executed",
            "payload": task.payload,
        }
        return WorkerResultV1(success=True, output=output)
