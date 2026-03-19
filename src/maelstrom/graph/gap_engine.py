"""Gap Engine state definition and node signatures."""
from __future__ import annotations

from typing import Any, TypedDict


class GapEngineState(TypedDict, total=False):
    """Full state schema for the Gap Engine graph."""
    topic: str
    llm_config: dict[str, Any]
    session_id: str
    expanded_queries: list[str]
    raw_papers: list[dict]
    papers: list[dict]
    coverage_matrix: dict[str, Any]
    gap_hypotheses: list[dict]
    critic_results: list[dict]
    ranked_gaps: list[dict]
    topic_candidates: list[dict]
    search_result: dict[str, Any]
    current_step: str
    error: str | None


# --- Placeholder node functions ---

def topic_intake(state: GapEngineState) -> GapEngineState:
    """Validate and normalize input topic."""
    state["current_step"] = "topic_intake"
    return state


def query_expansion(state: GapEngineState) -> GapEngineState:
    """Expand topic into multiple search queries."""
    state["current_step"] = "query_expansion"
    if not state.get("expanded_queries"):
        state["expanded_queries"] = [state.get("topic", "")]
    return state


def paper_retrieval(state: GapEngineState) -> GapEngineState:
    """Retrieve papers from multiple sources."""
    state["current_step"] = "paper_retrieval"
    if "raw_papers" not in state:
        state["raw_papers"] = []
    return state


def normalize_dedup(state: GapEngineState) -> GapEngineState:
    """Cross-source deduplication of papers."""
    state["current_step"] = "normalize_dedup"
    state["papers"] = state.get("raw_papers", [])
    return state
def coverage_matrix(state: GapEngineState) -> GapEngineState:
    """Build task-method-dataset-metric coverage matrix."""
    state["current_step"] = "coverage_matrix"
    if "coverage_matrix" not in state:
        state["coverage_matrix"] = {}
    return state


def gap_hypothesis(state: GapEngineState) -> GapEngineState:
    """Generate gap hypotheses via LLM."""
    state["current_step"] = "gap_hypothesis"
    if "gap_hypotheses" not in state:
        state["gap_hypotheses"] = []
    return state


def gap_critic(state: GapEngineState) -> GapEngineState:
    """Critique and validate gap hypotheses."""
    state["current_step"] = "gap_critic"
    if "critic_results" not in state:
        state["critic_results"] = []
    return state


def ranking_packaging(state: GapEngineState) -> GapEngineState:
    """Rank gaps and produce final topic candidates."""
    state["current_step"] = "ranking_packaging"
    if "ranked_gaps" not in state:
        state["ranked_gaps"] = []
    if "topic_candidates" not in state:
        state["topic_candidates"] = []
    return state


# --- Edge routing ---

def should_continue_after_retrieval(state: GapEngineState) -> str:
    """Route after paper_retrieval: normalize_dedup if papers found, else error_end."""
    if state.get("error"):
        return "error_end"
    raw = state.get("raw_papers", [])
    if len(raw) > 0:
        return "normalize_dedup"
    return "error_end"


# All node functions for easy iteration
NODE_FUNCTIONS = {
    "topic_intake": topic_intake,
    "query_expansion": query_expansion,
    "paper_retrieval": paper_retrieval,
    "normalize_dedup": normalize_dedup,
    "coverage_matrix": coverage_matrix,
    "gap_hypothesis": gap_hypothesis,
    "gap_critic": gap_critic,
    "ranking_packaging": ranking_packaging,
}
