"""Register built-in MCP tools wrapping existing adapters and services."""
from __future__ import annotations

import json

from maelstrom.mcp.registry import get_registry
from maelstrom.mcp.schemas import ResourceProvider, ToolDefinition


def register_builtin_tools() -> None:
    registry = get_registry()

    # ── Retrieval tools ───────────────────────────────────────────────

    registry.register(
        ToolDefinition(
            name="paper_search",
            description="Search academic papers across Arxiv, Semantic Scholar, OpenAlex, and OpenReview",
            category="retrieval",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
            required_params=["query"],
        ),
        _paper_search,
    )

    registry.register(
        ToolDefinition(
            name="evidence_search",
            description="Search evidence memory (FTS) for a session",
            category="retrieval",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["session_id", "query"],
            },
            required_params=["session_id", "query"],
        ),
        _evidence_search,
    )

    # ── LLM tools ─────────────────────────────────────────────────────

    registry.register(
        ToolDefinition(
            name="llm_call",
            description="Call the configured LLM with a prompt",
            category="llm",
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "max_tokens": {"type": "integer", "default": 4096},
                },
                "required": ["prompt"],
            },
            required_params=["prompt"],
        ),
        _llm_call,
    )

    # ── Storage tools ─────────────────────────────────────────────────

    registry.register(
        ToolDefinition(
            name="artifact_store",
            description="Store an artifact for a session",
            category="storage",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "type": {"type": "string"},
                    "data": {"type": "object"},
                },
                "required": ["session_id", "type"],
            },
            required_params=["session_id", "type"],
        ),
        _artifact_store,
    )

    # ── Context tools ─────────────────────────────────────────────────

    registry.register(
        ToolDefinition(
            name="session_context",
            description="Get session metadata, current phase, and run summaries",
            category="context",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                },
                "required": ["session_id"],
            },
            required_params=["session_id"],
        ),
        _session_context,
    )

    registry.register(
        ToolDefinition(
            name="gap_results",
            description="Get the latest gap analysis results for a session",
            category="context",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                },
                "required": ["session_id"],
            },
            required_params=["session_id"],
        ),
        _gap_results,
    )

    registry.register(
        ToolDefinition(
            name="synthesis_results",
            description="Get the latest synthesis results for a session",
            category="context",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                },
                "required": ["session_id"],
            },
            required_params=["session_id"],
        ),
        _synthesis_results,
    )

    # ── Resource Providers ────────────────────────────────────────────

    registry.register_provider(ResourceProvider(
        name="academic_papers",
        provider_type="paper_search",
        description="Multi-source academic paper search (Arxiv, S2, OpenAlex, OpenReview)",
    ))

    registry.register_provider(ResourceProvider(
        name="evidence_memory",
        provider_type="memory",
        description="Session-scoped FTS evidence memory with graph edges",
    ))

    registry.register_provider(ResourceProvider(
        name="artifact_storage",
        provider_type="storage",
        description="Session-scoped artifact persistence (SQLite)",
    ))


# ── Tool handlers ─────────────────────────────────────────────────────


async def _paper_search(query: str, max_results: int = 10) -> dict:
    from maelstrom.adapters import ArxivAdapter, SemanticScholarAdapter, OpenAlexAdapter, OpenReviewAdapter
    from maelstrom.services.paper_retriever import PaperRetriever
    retriever = PaperRetriever([ArxivAdapter(), SemanticScholarAdapter(), OpenAlexAdapter(), OpenReviewAdapter()])
    result = await retriever.search_with_fallback(query, max_results=max_results)
    return {"papers": result.get("papers", []), "count": len(result.get("papers", []))}


async def _llm_call(prompt: str, max_tokens: int = 4096) -> dict:
    from maelstrom.services.llm_client import call_llm
    from maelstrom.services.llm_config_service import get_config
    cfg = get_config()
    profile = cfg.get_active_profile()
    if not profile:
        return {"error": "No active LLM profile"}
    text = await call_llm(prompt, profile.model_dump(), max_tokens=max_tokens)
    return {"text": text}


async def _evidence_search(session_id: str, query: str, limit: int = 10) -> dict:
    from maelstrom.services.evidence_memory import get_evidence_memory
    mem = get_evidence_memory()
    hits = await mem.search(session_id, query, limit=limit)
    return {"hits": [h.model_dump() for h in hits]}


async def _artifact_store(session_id: str, type: str, data: dict | None = None) -> dict:
    from maelstrom.db import artifact_repo, session_repo
    from maelstrom.db.database import get_db
    db = await get_db()
    artifact = await artifact_repo.create_artifact(db, session_id, type, json.dumps(data or {}))
    await session_repo.touch_session(db, session_id)
    return artifact


async def _session_context(session_id: str) -> dict:
    from maelstrom.db import session_repo, gap_run_repo, synthesis_run_repo, planning_run_repo, experiment_run_repo
    from maelstrom.db.database import get_db
    from maelstrom.services.phase_tracker import get_current_phase
    db = await get_db()
    session = await session_repo.get_session(db, session_id)
    if not session:
        return {"error": "Session not found"}
    phase = await get_current_phase(session_id)
    gap_runs = await gap_run_repo.list_by_session(db, session_id, limit=5)
    synthesis_runs = await synthesis_run_repo.list_by_session(db, session_id, limit=5)
    planning_runs = await planning_run_repo.list_by_session(db, session_id, limit=5)
    experiment_runs = await experiment_run_repo.list_by_session(db, session_id, limit=5)
    return {
        "session_id": session_id,
        "title": session["title"],
        "current_phase": phase.value,
        "gap_runs": [{"id": r["id"], "status": r["status"], "topic": r["topic"]} for r in gap_runs],
        "synthesis_runs": [{"id": r["id"], "status": r["status"], "topic": r.get("topic", "")} for r in synthesis_runs],
        "planning_runs": [{"id": r["id"], "status": r["status"], "topic": r.get("topic", "")} for r in planning_runs],
        "experiment_runs": [{"id": r["id"], "status": r["status"], "topic": r.get("topic", "")} for r in experiment_runs],
    }


async def _gap_results(session_id: str) -> dict:
    from maelstrom.db import gap_run_repo
    from maelstrom.db.database import get_db
    from maelstrom.services import gap_service
    db = await get_db()
    runs = await gap_run_repo.list_by_session(db, session_id, limit=1)
    if not runs:
        return {"error": "No gap runs found"}
    latest = runs[0]
    if latest["status"] != "completed":
        return {"run_id": latest["id"], "status": latest["status"]}
    result = await gap_service.get_result(latest["id"])
    return {"run_id": latest["id"], "result": result}


async def _synthesis_results(session_id: str) -> dict:
    from maelstrom.db import synthesis_run_repo
    from maelstrom.db.database import get_db
    from maelstrom.services import synthesis_service
    db = await get_db()
    runs = await synthesis_run_repo.list_by_session(db, session_id, limit=1)
    if not runs:
        return {"error": "No synthesis runs found"}
    latest = runs[0]
    if latest["status"] != "completed":
        return {"run_id": latest["id"], "status": latest["status"]}
    result = await synthesis_service.get_result(latest["id"])
    return {"run_id": latest["id"], "result": result}
