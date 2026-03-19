"""Gap Engine graph builder.

Uses langgraph StateGraph when available, otherwise falls back to a
lightweight in-process runner so the graph structure is testable without
the langgraph dependency (which requires Python 3.11+).
"""
from __future__ import annotations

from typing import Any, Callable

from maelstrom.graph.gap_engine import (
    GapEngineState,
    NODE_FUNCTIONS,
    should_continue_after_retrieval,
)

# Ordered node names defining the linear pipeline
NODE_ORDER = [
    "topic_intake",
    "query_expansion",
    "paper_retrieval",
    # conditional edge here
    "normalize_dedup",
    "coverage_matrix",
    "gap_hypothesis",
    "gap_critic",
    "ranking_packaging",
]

# Edge after paper_retrieval is conditional
CONDITIONAL_EDGE_SOURCE = "paper_retrieval"


class GapEngineGraph:
    """Compiled Gap Engine graph — runs nodes in order with conditional routing."""

    def __init__(
        self,
        nodes: dict[str, Callable],
        node_order: list[str],
        conditional_edges: dict[str, Callable] | None = None,
        checkpointer: Any = None,
    ) -> None:
        self.nodes = nodes
        self.node_order = node_order
        self.conditional_edges = conditional_edges or {}
        self.checkpointer = checkpointer

    def invoke(self, state: GapEngineState) -> GapEngineState:
        """Execute the graph synchronously."""
        i = 0
        while i < len(self.node_order):
            name = self.node_order[i]
            fn = self.nodes[name]
            state = fn(state)
            # Check conditional edge
            if name in self.conditional_edges:
                route_fn = self.conditional_edges[name]
                target = route_fn(state)
                if target == "error_end":
                    state["error"] = state.get("error") or "No papers found"
                    state["current_step"] = "error_end"
                    return state
                # Otherwise continue to the target node (next in order)
            i += 1
        return state


def build_gap_engine_graph(checkpointer: Any = None) -> GapEngineGraph:
    """Build and return the compiled Gap Engine graph."""
    return GapEngineGraph(
        nodes=dict(NODE_FUNCTIONS),
        node_order=list(NODE_ORDER),
        conditional_edges={
            CONDITIONAL_EDGE_SOURCE: should_continue_after_retrieval,
        },
        checkpointer=checkpointer,
    )
