"""query_expansion node — use LLM to generate search query variants."""
from __future__ import annotations

import json
import logging

from maelstrom.graph.gap_engine import GapEngineState
from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

_EXPANSION_PROMPT = """You are an academic research assistant. Given a research topic, generate {n} diverse search queries for finding relevant papers. Each query should approach the topic from a different angle:
- Synonyms and alternative terminology
- Sub-fields and specific methods
- Broader context and applications
- Related datasets or benchmarks

Topic: {topic}

Return ONLY a JSON array of strings, no explanation. Example: ["query 1", "query 2", "query 3"]"""


async def query_expansion(state: GapEngineState) -> GapEngineState:
    """Expand topic into multiple search queries using LLM."""
    state["current_step"] = "query_expansion"
    topic = state.get("topic", "")
    llm_config = state.get("llm_config", {})
    n_queries = 4

    queries: list[str] = [topic]  # Always include original

    try:
        prompt = _EXPANSION_PROMPT.format(topic=topic, n=n_queries)
        raw = await call_llm(prompt, llm_config, max_tokens=1024, timeout=30.0)
        # Parse JSON array from response
        parsed = json.loads(raw.strip())
        if isinstance(parsed, list):
            for q in parsed:
                q_str = str(q).strip()
                if q_str and q_str != topic and q_str not in queries:
                    queries.append(q_str)
    except Exception as e:
        logger.warning("Query expansion failed, using original topic only: %s", e)

    state["expanded_queries"] = queries
    return state
