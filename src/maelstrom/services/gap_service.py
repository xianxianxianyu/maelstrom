"""Gap Engine service — orchestrate gap analysis runs."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from maelstrom.db import gap_run_repo, run_paper_repo
from maelstrom.db.database import get_db
from maelstrom.schemas.llm_config import LLMProfile
from maelstrom.services.event_bus import get_event_bus

logger = logging.getLogger(__name__)

# In-memory run state (current_step, full result)
_run_state: dict[str, dict[str, Any]] = {}


async def start_run(session_id: str, topic: str, profile: LLMProfile) -> str:
    """Create a gap run record and launch background execution."""
    db = await get_db()
    run = await gap_run_repo.create_gap_run(db, session_id, topic)
    run_id = run["id"]
    _run_state[run_id] = {"current_step": "pending", "result": None, "error": None}
    asyncio.create_task(_execute_run(run_id, session_id, topic, profile))
    return run_id


async def get_status(run_id: str) -> dict | None:
    db = await get_db()
    run = await gap_run_repo.get_gap_run(db, run_id)
    if not run:
        return None
    mem = _run_state.get(run_id, {})
    current_step = mem.get("current_step") or run.get("current_step") or run["status"]
    return {
        "run_id": run_id,
        "status": run["status"],
        "current_step": current_step,
    }


async def get_result(run_id: str) -> dict | None:
    db = await get_db()
    run = await gap_run_repo.get_gap_run(db, run_id)
    if not run:
        return None
    if run["status"] != "completed":
        return {"status": run["status"]}
    return json.loads(run["result_json"])


async def get_papers(run_id: str, offset: int = 0, limit: int = 50) -> list[dict]:
    db = await get_db()
    rows = await run_paper_repo.list_by_run(db, run_id)
    papers = [json.loads(r["paper_json"]) for r in rows]
    return papers[offset:offset + limit]


async def get_matrix(run_id: str) -> dict | None:
    result = await get_result(run_id)
    if not result or "coverage_matrix" not in result:
        return None
    return result["coverage_matrix"]


def subscribe(run_id: str) -> asyncio.Queue:
    bus = get_event_bus()
    return bus.subscribe(run_id)


def unsubscribe(run_id: str, q: asyncio.Queue) -> None:
    bus = get_event_bus()
    bus.unsubscribe(run_id, q)


async def rehydrate_run_state(run_id: str) -> None:
    """Reload run state from DB into _run_state (e.g. after restart)."""
    db = await get_db()
    run = await gap_run_repo.get_gap_run(db, run_id)
    if not run:
        return
    _run_state[run_id] = {
        "current_step": run.get("current_step") or run["status"],
        "result": json.loads(run["result_json"]) if run.get("result_json") and run["result_json"] != "{}" else None,
        "error": None,
    }


async def stream_events(run_id: str):
    """Async generator that yields SSE events for a run."""
    bus = get_event_bus()
    q = bus.subscribe(run_id)
    try:
        while True:
            event = await q.get()
            if event["event"] == "__done__":
                break
            yield event
    finally:
        bus.unsubscribe(run_id, q)


async def _execute_run(run_id: str, session_id: str, topic: str, profile: LLMProfile) -> None:
    """Background task: run the Gap Engine graph."""
    db = await get_db()
    bus = get_event_bus()

    async def _emit(event: str, data: dict, node_name: str = "") -> None:
        await bus.emit(run_id, event, data, session_id=session_id, engine="gap", node_name=node_name)

    try:
        await gap_run_repo.update_gap_run_status(db, run_id, "running")

        state = {
            "topic": topic,
            "session_id": session_id,
            "llm_config": profile.model_dump(),
        }

        from maelstrom.graph.nodes.topic_intake import topic_intake as ti_fn
        from maelstrom.graph.nodes.query_expansion import query_expansion as qe_fn
        from maelstrom.graph.nodes.paper_retrieval import paper_retrieval as pr_fn
        from maelstrom.graph.nodes.normalize_dedup import normalize_dedup as nd_fn
        from maelstrom.graph.nodes.coverage_matrix import coverage_matrix as cm_fn
        from maelstrom.graph.nodes.gap_hypothesis import gap_hypothesis as gh_fn
        from maelstrom.graph.nodes.gap_critic import gap_critic as gc_fn
        from maelstrom.graph.nodes.ranking_packaging import ranking_packaging as rp_fn

        from maelstrom.adapters import ArxivAdapter, SemanticScholarAdapter, OpenAlexAdapter, OpenReviewAdapter
        from maelstrom.services.paper_retriever import PaperRetriever
        retriever = PaperRetriever([
            ArxivAdapter(), SemanticScholarAdapter(), OpenAlexAdapter(), OpenReviewAdapter(),
        ])

        steps = [
            ("topic_intake", lambda s: ti_fn(s)),
            ("query_expansion", lambda s: qe_fn(s)),
            ("paper_retrieval", lambda s: pr_fn(s, retriever=retriever)),
            ("normalize_dedup", lambda s: nd_fn(s)),
            ("coverage_matrix", lambda s: cm_fn(s)),
            ("gap_hypothesis", lambda s: gh_fn(s)),
            ("gap_critic", lambda s: gc_fn(s)),
            ("ranking_packaging", lambda s: rp_fn(s)),
        ]

        for idx, (step_name, step_fn) in enumerate(steps):
            _run_state[run_id]["current_step"] = step_name
            await _emit("step_start", {"step": step_name, "index": idx}, node_name=step_name)

            result = step_fn(state)
            if asyncio.iscoroutine(result):
                state = await result
            else:
                state = result

            if state.get("error"):
                await _emit("error", {"message": state["error"], "step": step_name}, node_name=step_name)
                raise RuntimeError(state["error"])

            await _emit("step_complete", {"step": step_name, "summary": f"{step_name} done"}, node_name=step_name)

            # Persist node-level checkpoint
            completed_steps = [s[0] for s in steps[:idx + 1]]
            try:
                await gap_run_repo.update_gap_run_progress(
                    db, run_id, step_name,
                    json.dumps({"completed_steps": completed_steps, "last_step": step_name}),
                )
            except Exception as exc:
                logger.warning("Progress checkpoint failed: %s", exc)

            if step_name == "normalize_dedup":
                papers = state.get("papers", [])
                sr = state.get("search_result", {})
                await _emit("papers_found", {"count": len(papers), "papers": papers, "sources": sr.get("source_statuses", [])})
            elif step_name == "coverage_matrix":
                cm = state.get("coverage_matrix", {})
                await _emit("matrix_ready", {"coverage_matrix": cm, "summary": cm.get("summary", {})})
            elif step_name == "gap_hypothesis":
                for gap in state.get("gap_hypotheses", []):
                    await _emit("gap_found", {"gap": gap})

        # Persist papers
        papers = state.get("papers", [])
        if papers:
            paper_jsons = [json.dumps(p) for p in papers]
            await run_paper_repo.bulk_create_for_run(db, run_id, paper_jsons)

        full_result = {
            "ranked_gaps": state.get("ranked_gaps", []),
            "topic_candidates": state.get("topic_candidates", []),
            "papers": papers,
            "coverage_matrix": state.get("coverage_matrix", {}),
            "search_result": state.get("search_result", {}),
        }
        await gap_run_repo.update_gap_run_result(db, run_id, json.dumps(full_result))
        await gap_run_repo.update_gap_run_status(db, run_id, "completed")
        _run_state[run_id]["current_step"] = "completed"
        _run_state[run_id]["result"] = full_result
        await _emit("run_completed", {"engine": "gap", "run_id": run_id})

        # Advance session phase
        try:
            from maelstrom.services.phase_tracker import advance_phase_on_completion
            from maelstrom.services.policy_service import get_policy_config
            policy = await get_policy_config(db, session_id)
            if policy.auto_advance_phase:
                await advance_phase_on_completion(session_id, "gap")
        except Exception as e:
            logger.warning("Phase advance failed: %s", e)

        # Write evidence edges: gap_item → supported_by → paper
        # Also ingest gaps into evidence memory for FTS search
        try:
            from maelstrom.services.policy_service import get_policy_config
            policy = await get_policy_config(db, session_id)
            if not policy.auto_evidence_writeback:
                raise Exception("Evidence writeback disabled by policy")
            from maelstrom.db import evidence_edge_repo
            from maelstrom.services.evidence_memory import get_evidence_memory
            mem = get_evidence_memory()
            for gap in full_result.get("ranked_gaps", []):
                gap_id = gap.get("gap_id", "")
                gap_title = gap.get("title", gap.get("gap_id", ""))
                gap_summary = gap.get("summary", "")
                gap_types = gap.get("gap_type", [])
                # Ingest gap into evidence memory for FTS
                if gap_id and gap_title:
                    content = f"{gap_summary}\nType: {', '.join(gap_types) if isinstance(gap_types, list) else gap_types}"
                    await mem.ingest_text(session_id, "gap", gap_id, gap_title, content)
                # Write edges
                for ref in gap.get("supporting_refs", gap.get("references", [])):
                    paper_id = ref if isinstance(ref, str) else ref.get("paper_id", "")
                    if gap_id and paper_id:
                        await evidence_edge_repo.create_edge(db, gap_id, "gap_item", paper_id, "paper", "supported_by")
        except Exception as e:
            logger.warning("Evidence edge writeback failed: %s", e)

        await _emit("result", {"gaps": full_result["ranked_gaps"], "candidates": full_result["topic_candidates"]})
        await _emit("__done__", {})

    except Exception as e:
        logger.exception("Gap run %s failed: %s", run_id, e)
        await gap_run_repo.update_gap_run_status(db, run_id, "failed")
        _run_state[run_id]["current_step"] = "failed"
        _run_state[run_id]["error"] = str(e)
        await _emit("run_failed", {"engine": "gap", "run_id": run_id, "error": str(e)})
        await _emit("error", {"message": str(e), "step": _run_state[run_id].get("current_step", "unknown")})
        await _emit("__done__", {})
