"""Experiment Engine service — orchestrate experiment runs."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from maelstrom.db import experiment_run_repo
from maelstrom.db.database import get_db
from maelstrom.schemas.llm_config import LLMProfile
from maelstrom.services.event_bus import get_event_bus

logger = logging.getLogger(__name__)

_run_state: dict[str, dict[str, Any]] = {}


async def start_run(
    session_id: str, topic: str, profile: LLMProfile,
    plan_id: str | None = None,
) -> str:
    db = await get_db()
    run = await experiment_run_repo.create_experiment_run(db, session_id, topic, source_plan_id=plan_id)
    run_id = run["id"]
    _run_state[run_id] = {"current_step": "pending", "result": None, "error": None}
    asyncio.create_task(_execute_run(run_id, session_id, topic, profile, plan_id))
    return run_id


async def get_status(run_id: str) -> dict | None:
    db = await get_db()
    run = await experiment_run_repo.get_experiment_run(db, run_id)
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
    run = await experiment_run_repo.get_experiment_run(db, run_id)
    if not run:
        return None
    if run["status"] != "completed":
        return {"status": run["status"]}
    return json.loads(run["result_json"])


def subscribe(run_id: str) -> asyncio.Queue:
    return get_event_bus().subscribe(run_id)


def unsubscribe(run_id: str, q: asyncio.Queue) -> None:
    get_event_bus().unsubscribe(run_id, q)


async def rehydrate_run_state(run_id: str) -> None:
    """Reload run state from DB into _run_state (e.g. after restart)."""
    db = await get_db()
    run = await experiment_run_repo.get_experiment_run(db, run_id)
    if not run:
        return
    _run_state[run_id] = {
        "current_step": run.get("current_step") or run["status"],
        "result": json.loads(run["result_json"]) if run.get("result_json") and run["result_json"] != "{}" else None,
        "error": None,
    }


async def _execute_run(
    run_id: str, session_id: str, topic: str,
    profile: LLMProfile, plan_id: str | None = None,
) -> None:
    db = await get_db()
    bus = get_event_bus()

    async def _emit(event: str, data: dict, node_name: str = "") -> None:
        await bus.emit(run_id, event, data, session_id=session_id, engine="experiment", node_name=node_name)

    try:
        await experiment_run_repo.update_experiment_run_status(db, run_id, "running")

        from maelstrom.graph import experiment_engine as nodes

        state: dict[str, Any] = {
            "run_id": run_id,
            "session_id": session_id,
            "topic": topic,
            "source_plan_id": plan_id,
            "llm_config": profile.model_dump(),
        }

        if plan_id:
            try:
                from maelstrom.db import planning_run_repo
                plan_run = await planning_run_repo.get_planning_run(db, plan_id)
                if plan_run and plan_run["result_json"]:
                    plan_result = json.loads(plan_run["result_json"])
                    state["plan"] = plan_result.get("plan", {})
                    state["claims"] = plan_result.get("claims", [])
            except Exception as e:
                logger.warning("Failed to load planning result: %s", e)

        steps = [
            ("config_capture", nodes.config_capture),
            ("metrics_ingestion", nodes.metrics_ingestion),
            ("result_normalization", nodes.result_normalization),
            ("conclusion_generation", nodes.conclusion_generation),
            ("evidence_binding", nodes.evidence_binding),
            ("claim_critique", nodes.claim_critique),
            ("reflection_summary", nodes.reflection_summary),
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
                await experiment_run_repo.update_experiment_run_progress(
                    db, run_id, step_name,
                    json.dumps({"completed_steps": completed_steps, "last_step": step_name}),
                )
            except Exception as exc:
                logger.warning("Progress checkpoint failed: %s", exc)

        # HITL gate: conclusion_review after conclusion_generation
        try:
            from maelstrom.services.policy_service import get_policy_config
            from maelstrom.services.hitl_manager import get_hitl_manager
            policy = await get_policy_config(db, session_id)
            if policy.conclusion_review:
                await _emit("approval_pending", {"type": "conclusion_review"})
                manager = get_hitl_manager()
                conclusion = state.get("conclusion", {})
                decision = await manager.request_approval(
                    db, session_id, run_id, "conclusion_review",
                    {"summary": conclusion.get("summary", "") if isinstance(conclusion, dict) else str(conclusion)[:500]},
                )
                if decision == "rejected":
                    raise RuntimeError("Conclusion rejected by reviewer")
        except RuntimeError:
            raise
        except Exception as e:
            logger.warning("HITL gate skipped: %s", e)

        # Persist result
        result = {
            "conclusion": state.get("conclusion"),
            "reflection": state.get("reflection"),
            "metrics": state.get("metrics", []),
            "normalized_metrics": state.get("normalized_metrics", []),
            "claim_verdicts": state.get("claim_verdicts", []),
            "config_snapshot": state.get("config_snapshot", {}),
        }
        await experiment_run_repo.update_experiment_run_result(db, run_id, json.dumps(result, default=str))
        await experiment_run_repo.update_experiment_run_status(db, run_id, "completed")
        _run_state[run_id]["current_step"] = "completed"
        _run_state[run_id]["result"] = result
        await _emit("run_completed", {"engine": "experiment", "run_id": run_id})

        # Advance session phase
        try:
            from maelstrom.services.phase_tracker import advance_phase_on_completion
            from maelstrom.services.policy_service import get_policy_config as _get_policy
            _policy = await _get_policy(db, session_id)
            if _policy.auto_advance_phase:
                await advance_phase_on_completion(session_id, "experiment")
        except Exception as e:
            logger.warning("Phase advance failed: %s", e)

        # Persist artifacts
        try:
            from maelstrom.db import artifact_repo, session_repo
            conclusion = state.get("conclusion")
            if conclusion:
                await artifact_repo.create_artifact(db, session_id, "conclusion", json.dumps(conclusion, default=str))
                await _emit("artifact_created", {"artifact_type": "conclusion", "session_id": session_id})
            reflection = state.get("reflection")
            if reflection:
                await artifact_repo.create_artifact(db, session_id, "reflection_note", json.dumps(reflection, default=str))
                await _emit("artifact_created", {"artifact_type": "reflection_note", "session_id": session_id})
            await session_repo.touch_session(db, session_id)
        except Exception as e:
            logger.warning("Artifact persistence failed: %s", e)

        # Write to EvidenceMemory
        try:
            from maelstrom.services.policy_service import get_policy_config as _get_pol
            _pol = await _get_pol(db, session_id)
            if not _pol.auto_evidence_writeback:
                raise Exception("Evidence writeback disabled by policy")
            from maelstrom.services.evidence_memory import get_evidence_memory
            mem = get_evidence_memory()
            conclusion = state.get("conclusion", {})
            if conclusion:
                await mem.ingest_text(
                    session_id, "experiment", run_id,
                    f"Conclusion: {conclusion.get('summary', '')}",
                    json.dumps(conclusion, default=str, ensure_ascii=False)[:3000],
                )
            reflection = state.get("reflection", {})
            if reflection:
                await mem.ingest_text(
                    session_id, "reflection", run_id,
                    f"Reflection: {', '.join(reflection.get('insights', [])[:3])}",
                    json.dumps(reflection, default=str, ensure_ascii=False)[:3000],
                )
        except Exception as e:
            logger.warning("EvidenceMemory writeback failed: %s", e)

        # Write evidence edges: conclusion → inferred_from → run
        try:
            from maelstrom.db import evidence_edge_repo
            conclusion_data = state.get("conclusion", {})
            if isinstance(conclusion_data, dict) and conclusion_data:
                conclusion_id = conclusion_data.get("conclusion_id", run_id)
                await evidence_edge_repo.create_edge(db, conclusion_id, "conclusion", run_id, "experiment_run", "inferred_from")
        except Exception as e:
            logger.warning("Evidence edge writeback failed: %s", e)

        # Update session phase
        try:
            from maelstrom.services.phase_tracker import _set_phase
            from maelstrom.schemas.common import ResearchPhase
            await _set_phase(db, session_id, ResearchPhase.execution)
        except Exception as e:
            logger.warning("Phase update failed: %s", e)

        await _emit("result", result)
        await _emit("__done__", {})

    except Exception as e:
        logger.exception("Experiment run %s failed: %s", run_id, e)
        await experiment_run_repo.update_experiment_run_status(db, run_id, "failed")
        _run_state[run_id]["current_step"] = "failed"
        _run_state[run_id]["error"] = str(e)
        await _emit("run_failed", {"engine": "experiment", "run_id": run_id, "error": str(e)})
        await _emit("error", {"message": str(e), "step": _run_state[run_id].get("current_step", "unknown")})
        await _emit("__done__", {})
