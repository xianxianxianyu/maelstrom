"""P1-05: Gap Engine graph definition tests."""
from __future__ import annotations

import pytest

from maelstrom.graph.gap_engine import (
    GapEngineState,
    NODE_FUNCTIONS,
    should_continue_after_retrieval,
)
from maelstrom.graph.builder import (
    GapEngineGraph,
    NODE_ORDER,
    build_gap_engine_graph,
)


def test_state_schema():
    """GapEngineState contains all required fields."""
    required = [
        "topic", "llm_config", "session_id", "expanded_queries",
        "raw_papers", "papers", "coverage_matrix", "gap_hypotheses",
        "critic_results", "ranked_gaps", "topic_candidates",
        "search_result", "current_step", "error",
    ]
    annotations = GapEngineState.__annotations__
    for field in required:
        assert field in annotations, f"Missing field: {field}"


def test_graph_compiles():
    """Graph builds without error."""
    graph = build_gap_engine_graph()
    assert isinstance(graph, GapEngineGraph)


def test_graph_node_count():
    """Graph has exactly 8 nodes."""
    graph = build_gap_engine_graph()
    assert len(graph.nodes) == 8


def test_graph_edge_order():
    """Nodes are connected in the correct order."""
    expected = [
        "topic_intake", "query_expansion", "paper_retrieval",
        "normalize_dedup", "coverage_matrix", "gap_hypothesis",
        "gap_critic", "ranking_packaging",
    ]
    assert NODE_ORDER == expected
def test_route_with_papers():
    """With raw_papers, route to normalize_dedup."""
    state: GapEngineState = {"raw_papers": [{"title": "paper"}]}
    assert should_continue_after_retrieval(state) == "normalize_dedup"


def test_route_no_papers():
    """Without raw_papers, route to error_end."""
    state: GapEngineState = {"raw_papers": []}
    assert should_continue_after_retrieval(state) == "error_end"


def test_route_with_error():
    """With error set, route to error_end."""
    state: GapEngineState = {"raw_papers": [{"title": "p"}], "error": "something broke"}
    assert should_continue_after_retrieval(state) == "error_end"


def test_checkpoint_configured():
    """Checkpointer is stored on the graph."""
    sentinel = object()
    graph = build_gap_engine_graph(checkpointer=sentinel)
    assert graph.checkpointer is sentinel


def test_passthrough_execution():
    """Full graph executes with placeholder nodes without error."""
    graph = build_gap_engine_graph()
    state: GapEngineState = {
        "topic": "transformer efficiency",
        "raw_papers": [{"title": "paper1"}],
    }
    result = graph.invoke(state)
    assert result["current_step"] == "ranking_packaging"
    assert result.get("error") is None
    assert "papers" in result
    assert "ranked_gaps" in result
    assert "topic_candidates" in result


def test_passthrough_execution_error_route():
    """Graph stops at error_end when no papers found."""
    graph = build_gap_engine_graph()
    state: GapEngineState = {
        "topic": "nonexistent topic",
        "raw_papers": [],
    }
    result = graph.invoke(state)
    assert result["current_step"] == "error_end"
    assert result.get("error") is not None
