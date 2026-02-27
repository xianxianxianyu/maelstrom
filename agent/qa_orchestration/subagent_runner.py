from __future__ import annotations

import uuid
from typing import Any

from .contracts import SubagentResult, SubagentRunContext, SubagentTask
from .subagent_registry import SubagentRegistry


class SubagentRunner:
    def __init__(self, registry: SubagentRegistry) -> None:
        self.registry = registry

    async def run_plan(
        self,
        session_id: str,
        turn_id: str,
        trace_id: str,
        query: str,
        sub_problems: list[dict[str, Any]],
        selected_context: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], float]:
        results_by_id: dict[str, Any] = {}
        run_records: list[dict[str, Any]] = []
        citations: list[dict[str, Any]] = []

        for problem in sub_problems:
            problem_id = str(problem["sub_problem_id"])
            capability = str(problem["agent_capability"])
            dependencies = [str(dep) for dep in problem.get("depends_on", [])]
            dependency_results = {dep: results_by_id.get(dep) for dep in dependencies}

            task = SubagentTask(
                task_id=f"task_{uuid.uuid4().hex[:10]}",
                turn_id=turn_id,
                query=str(problem.get("question", query)),
                capability=capability,
                payload={"problem": problem, "original_query": query},
            )
            context = SubagentRunContext(
                session_id=session_id,
                trace_id=trace_id,
                selected_context=selected_context,
                dependency_results=dependency_results,
            )

            agent = self.registry.resolve(capability)
            result = await agent.run(task, context)

            results_by_id[problem_id] = result.output
            run_records.append(
                {
                    "sub_problem_id": problem_id,
                    "capability": capability,
                    "agent": agent.name,
                    "success": result.success,
                    "error": result.error,
                    "output": result.output,
                }
            )
            citations.extend(result.citations)

            if not result.success:
                break

        final_answer = self._build_answer(results_by_id, run_records)
        success_count = sum(1 for item in run_records if item["success"])
        confidence = round(success_count / max(len(run_records), 1), 4)
        return final_answer, run_records, citations, confidence

    def _build_answer(self, results_by_id: dict[str, Any], run_records: list[dict[str, Any]]) -> str:
        if not run_records:
            return "未生成有效结果"

        last_output = run_records[-1].get("output") or {}
        if isinstance(last_output, dict) and last_output.get("answer"):
            return str(last_output["answer"])

        parts: list[str] = []
        for item in run_records:
            output = item.get("output")
            if isinstance(output, dict):
                text = output.get("text") or output.get("summary") or output.get("answer")
                if text:
                    parts.append(str(text))
        return "\n".join(parts).strip() or "未生成有效结果"


class RetrievalSubagent:
    name = "retrieval-subagent"
    capabilities = {"context.retrieve"}

    async def run(self, task: SubagentTask, context: SubagentRunContext) -> SubagentResult:
        snippets = [item.get("summary", "") for item in context.selected_context[:3] if item.get("summary")]
        output = {
            "text": "\n".join(snippets) if snippets else "未命中历史上下文，使用当前问题继续处理",
            "selected_turn_ids": [item.get("turn_id") for item in context.selected_context[:3]],
        }
        citations = [
            {"source": item.get("turn_id"), "score": item.get("score", 0.0)}
            for item in context.selected_context[:3]
        ]
        return SubagentResult(success=True, output=output, citations=citations)


class ReasoningSubagent:
    name = "reasoning-subagent"
    capabilities = {"reasoning.synthesize"}

    async def run(self, task: SubagentTask, context: SubagentRunContext) -> SubagentResult:
        sections: list[str] = []
        for dep, output in context.dependency_results.items():
            if not isinstance(output, dict):
                continue
            text = output.get("text") or output.get("summary") or output.get("answer")
            if text:
                sections.append(f"[{dep}] {text}")
        text = "\n".join(sections).strip() or "暂无依赖结果，直接进入响应阶段"
        return SubagentResult(success=True, output={"summary": text})


class ResponseSubagent:
    name = "response-subagent"
    capabilities = {"response.compose"}

    async def run(self, task: SubagentTask, context: SubagentRunContext) -> SubagentResult:
        context_text: list[str] = []
        for output in context.dependency_results.values():
            if not isinstance(output, dict):
                continue
            text = output.get("summary") or output.get("text")
            if text:
                context_text.append(str(text))
        if context_text:
            answer = f"基于上下文分析，结论如下：\n{chr(10).join(context_text)}"
        else:
            answer = f"已记录问题：{task.query}。当前没有足够历史上下文，将按新问题处理。"
        return SubagentResult(success=True, output={"answer": answer})
