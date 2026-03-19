"""Synthesis Engine graph builder — 7-node sequential pipeline."""
from __future__ import annotations

from typing import Any, Callable

from maelstrom.graph import synthesis_engine as nodes_module

NODE_ORDER = [
    "targeted_retrieval",
    "relevance_filtering",
    "claim_extraction",
    "citation_binding",
    "conflict_analysis",
    "feasibility_review",
    "report_assembly",
]


class SynthesisEngineGraph:
    """Compiled Synthesis Engine graph — runs nodes in order."""

    NODES = list(NODE_ORDER)

    def __init__(self, checkpointer: Any = None) -> None:
        self.checkpointer = checkpointer

    async def run(self, state: dict, node_callback: Callable | None = None) -> dict:
        for node_name in self.NODES:
            if node_callback:
                await node_callback(node_name, "start")
            node_fn = getattr(nodes_module, node_name)
            state = await node_fn(state)
            if state.get("error"):
                break
            # Route check: no papers after targeted_retrieval → error
            if node_name == "targeted_retrieval" and not state.get("targeted_papers"):
                state["error"] = "No papers found for synthesis"
                break
            if node_callback:
                await node_callback(node_name, "complete")
        return state


def build_synthesis_engine_graph(checkpointer: Any = None) -> SynthesisEngineGraph:
    return SynthesisEngineGraph(checkpointer=checkpointer)
