"""Synthesis Engine service — orchestrate synthesis runs."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from maelstrom.db import synthesis_run_repo
from maelstrom.db.database import get_db
from maelstrom.schemas.llm_config import LLMProfile
from maelstrom.services.event_bus import get_event_bus

logger = logging.getLogger(__name__)

# In-memory run state
_run_state: dict[str, dict[str, Any]] = {}


async def start_run(
    session_id: str, topic: str, profile: LLMProfile,
    gap_id: str | None = None,
) -> str:
    db = await get_db()
    run = await synthesis_run_repo.create_synthesis_run(db, session_id, topic, source_gap_id=gap_id)
    run_id = run["id"]
    _run_state[run_id] = {"current_step": "pending", "result": None, "error": None}
    asyncio.create_task(_execute_run(run_id, session_id, topic, profile, gap_id))
    return run_id


async def get_status(run_id: str) -> dict | None:
    db = await get_db()
    run = await synthesis_run_repo.get_synthesis_run(db, run_id)
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
    run = await synthesis_run_repo.get_synthesis_run(db, run_id)
    if not run:
        return None
    if run["status"] != "completed":
        return {"status": run["status"]}
    return json.loads(run["result_json"])


async def rehydrate_run_state(run_id: str) -> None:
    """Reload run state from DB into _run_state (e.g. after restart)."""
    db = await get_db()
    run = await synthesis_run_repo.get_synthesis_run(db, run_id)
    if not run:
        return
    _run_state[run_id] = {
        "current_step": run.get("current_step") or run["status"],
        "result": json.loads(run["result_json"]) if run.get("result_json") and run["result_json"] != "{}" else None,
        "error": None,
    }


def subscribe(run_id: str) -> asyncio.Queue:
    return get_event_bus().subscribe(run_id)


def unsubscribe(run_id: str, q: asyncio.Queue) -> None:
    get_event_bus().unsubscribe(run_id, q)


async def _execute_run(
    run_id: str, session_id: str, topic: str,
    profile: LLMProfile, gap_id: str | None = None,
) -> None:
    db = await get_db()
    bus = get_event_bus()

    async def _emit(event: str, data: dict, node_name: str = "") -> None:
        await bus.emit(run_id, event, data, session_id=session_id, engine="synthesis", node_name=node_name)

    try:
        await synthesis_run_repo.update_synthesis_run_status(db, run_id, "running")

        from maelstrom.graph import synthesis_engine as nodes

        state: dict[str, Any] = {
            "run_id": run_id,
            "session_id": session_id,
            "topic": topic,
            "source_gap_id": gap_id,
            "llm_config": profile.model_dump(),
        }

        steps = [
            ("targeted_retrieval", nodes.targeted_retrieval),
            ("relevance_filtering", nodes.relevance_filtering),
            ("claim_extraction", nodes.claim_extraction),
            ("citation_binding", nodes.citation_binding),
            ("conflict_analysis", nodes.conflict_analysis),
            ("feasibility_review", nodes.feasibility_review),
            ("report_assembly", nodes.report_assembly),
        ]

        for idx, (step_name, step_fn) in enumerate(steps):
            _run_state[run_id]["current_step"] = step_name
            await _emit("step_start", {"step": step_name, "index": idx}, node_name=step_name)

            state = await step_fn(state)

            if state.get("error"):
                await _emit("error", {"message": state["error"], "step": step_name}, node_name=step_name)
                raise RuntimeError(state["error"])

            await _emit("step_complete", {"step": step_name, "summary": f"{step_name} done"}, node_name=step_name)

            # Persist node-level checkpoint
            completed_steps = [s[0] for s in steps[:idx + 1]]
            try:
                await synthesis_run_repo.update_synthesis_run_progress(
                    db, run_id, step_name,
                    json.dumps({"completed_steps": completed_steps, "last_step": step_name}),
                )
            except Exception as exc:
                logger.warning("Progress checkpoint failed: %s", exc)

            if step_name == "targeted_retrieval":
                papers = state.get("targeted_papers", [])
                if not papers:
                    raise RuntimeError("No papers found for synthesis")
                await _emit("papers_found", {"count": len(papers)})
            elif step_name == "claim_extraction":
                claims = state.get("claims", [])
                await _emit("claims_extracted", {"count": len(claims)})
            elif step_name == "conflict_analysis":
                for cp in state.get("conflict_points", []):
                    await _emit("conflict_found", {"conflict": cp if isinstance(cp, dict) else cp.model_dump()})

        # HITL gate: feasibility_approval after synthesis completes
        try:
            from maelstrom.services.policy_service import get_policy_config
            from maelstrom.services.hitl_manager import get_hitl_manager
            policy = await get_policy_config(db, session_id)
            if policy.feasibility_approval:
                await _emit("approval_pending", {"type": "feasibility_approval"})
                manager = get_hitl_manager()
                memo = state.get("feasibility_memo", {})
                decision = await manager.request_approval(
                    db, session_id, run_id, "feasibility_approval",
                    {"summary": memo.get("summary", "") if isinstance(memo, dict) else str(memo)[:500]},
                )
                if decision == "rejected":
                    raise RuntimeError("Feasibility assessment rejected by reviewer")
        except RuntimeError:
            raise
        except Exception as e:
            logger.warning("HITL gate skipped: %s", e)

        # Persist result
        result = {
            "review_report": state.get("review_report"),
            "feasibility_memo": state.get("feasibility_memo"),
            "claims": state.get("claims", []),
            "evidences": state.get("evidences", []),
            "consensus_points": state.get("consensus_points", []),
            "conflict_points": state.get("conflict_points", []),
        }
        await synthesis_run_repo.update_synthesis_run_result(db, run_id, json.dumps(result, default=str))
        await synthesis_run_repo.update_synthesis_run_status(db, run_id, "completed")
        _run_state[run_id]["current_step"] = "completed"
        _run_state[run_id]["result"] = result
        await _emit("run_completed", {"engine": "synthesis", "run_id": run_id})

        # Advance session phase
        try:
            from maelstrom.services.phase_tracker import advance_phase_on_completion
            from maelstrom.services.policy_service import get_policy_config as _get_policy
            _policy = await _get_policy(db, session_id)
            if _policy.auto_advance_phase:
                await advance_phase_on_completion(session_id, "synthesis")
        except Exception as e:
            logger.warning("Phase advance failed: %s", e)

        # Write FeasibilityMemo to EvidenceMemory
        try:
            from maelstrom.services.policy_service import get_policy_config as _get_pol
            _pol = await _get_pol(db, session_id)
            if not _pol.auto_evidence_writeback:
                raise Exception("Evidence writeback disabled by policy")
            from maelstrom.services.evidence_memory import get_evidence_memory
            memo = state.get("feasibility_memo")
            if memo and isinstance(memo, dict):
                mem = get_evidence_memory()
                await mem.ingest_text(
                    session_id, "feasibility", memo.get("memo_id", ""),
                    f"Feasibility: {memo.get('verdict', '')}",
                    f"{memo.get('reasoning', '')}\nVerdict: {memo.get('verdict', '')}\nConfidence: {memo.get('confidence', '')}",
                )
        except Exception as e:
            logger.warning("FeasibilityMemo writeback failed: %s", e)

        # Persist artifacts
        try:
            from maelstrom.db import artifact_repo, session_repo
            review = state.get("review_report")
            if review:
                await artifact_repo.create_artifact(db, session_id, "review_report", json.dumps(review, default=str))
                await _emit("artifact_created", {"artifact_type": "review_report", "session_id": session_id})
                await session_repo.touch_session(db, session_id)
        except Exception as e:
            logger.warning("Artifact persistence failed: %s", e)

        # Write evidence edges: claim → extracted_from → paper
        try:
            from maelstrom.db import evidence_edge_repo
            for claim in state.get("claims", []):
                claim_id = claim.get("claim_id", "") if isinstance(claim, dict) else ""
                sources = claim.get("source_papers", claim.get("sources", [])) if isinstance(claim, dict) else []
                for src in sources:
                    paper_id = src if isinstance(src, str) else src.get("paper_id", "")
                    if claim_id and paper_id:
                        await evidence_edge_repo.create_edge(db, claim_id, "claim", paper_id, "paper", "extracted_from")
        except Exception as e:
            logger.warning("Evidence edge writeback failed: %s", e)

        # Update session phase to grounding
        try:
            from maelstrom.services.phase_tracker import _set_phase
            from maelstrom.schemas.common import ResearchPhase
            await _set_phase(db, session_id, ResearchPhase.grounding)
        except Exception as e:
            logger.warning("Phase update failed: %s", e)

        await _emit("result", result)
        await _emit("__done__", {})

    except Exception as e:
        logger.exception("Synthesis run %s failed: %s", run_id, e)
        await synthesis_run_repo.update_synthesis_run_status(db, run_id, "failed")
        _run_state[run_id]["current_step"] = "failed"
        _run_state[run_id]["error"] = str(e)
        await _emit("run_failed", {"engine": "synthesis", "run_id": run_id, "error": str(e)})
        await _emit("error", {"message": str(e), "step": _run_state[run_id].get("current_step", "unknown")})
        await _emit("__done__", {})
