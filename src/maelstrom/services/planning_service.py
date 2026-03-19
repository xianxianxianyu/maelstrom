"""Planning Engine service — orchestrate planning runs."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from maelstrom.db import planning_run_repo
from maelstrom.db.database import get_db
from maelstrom.schemas.llm_config import LLMProfile
from maelstrom.services.event_bus import get_event_bus

logger = logging.getLogger(__name__)

_run_state: dict[str, dict[str, Any]] = {}


async def start_run(
    session_id: str, topic: str, profile: LLMProfile,
    synthesis_id: str | None = None,
) -> str:
    db = await get_db()
    run = await planning_run_repo.create_planning_run(db, session_id, topic, source_synthesis_id=synthesis_id)
    run_id = run["id"]
    _run_state[run_id] = {"current_step": "pending", "result": None, "error": None}
    asyncio.create_task(_execute_run(run_id, session_id, topic, profile, synthesis_id))
    return run_id


async def get_status(run_id: str) -> dict | None:
    db = await get_db()
    run = await planning_run_repo.get_planning_run(db, run_id)
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
    run = await planning_run_repo.get_planning_run(db, run_id)
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
    run = await planning_run_repo.get_planning_run(db, run_id)
    if not run:
        return
    _run_state[run_id] = {
        "current_step": run.get("current_step") or run["status"],
        "result": json.loads(run["result_json"]) if run.get("result_json") and run["result_json"] != "{}" else None,
        "error": None,
    }


async def _execute_run(
    run_id: str, session_id: str, topic: str,
    profile: LLMProfile, synthesis_id: str | None = None,
) -> None:
    db = await get_db()
    bus = get_event_bus()

    async def _emit(event: str, data: dict, node_name: str = "") -> None:
        await bus.emit(run_id, event, data, session_id=session_id, engine="planning", node_name=node_name)

    try:
        await planning_run_repo.update_planning_run_status(db, run_id, "running")

        from maelstrom.graph import planning_engine as nodes

        state: dict[str, Any] = {
            "run_id": run_id,
            "session_id": session_id,
            "topic": topic,
            "source_synthesis_id": synthesis_id,
            "llm_config": profile.model_dump(),
        }

        if synthesis_id:
            try:
                from maelstrom.db import synthesis_run_repo
                syn_run = await synthesis_run_repo.get_synthesis_run(db, synthesis_id)
                if syn_run and syn_run["result_json"]:
                    syn_result = json.loads(syn_run["result_json"])
                    state["review_report"] = syn_result.get("review_report")
                    state["feasibility_memo"] = syn_result.get("feasibility_memo")
                    state["claims"] = syn_result.get("claims", [])
            except Exception as e:
                logger.warning("Failed to load synthesis result: %s", e)

        steps = [
            ("task_framing", nodes.task_framing),
            ("baseline_generation", nodes.baseline_generation),
            ("dataset_protocol", nodes.dataset_protocol),
            ("metric_ablation", nodes.metric_ablation),
            ("risk_estimation", nodes.risk_estimation),
            ("plan_validation", nodes.plan_validation),
            ("plan_rendering", nodes.plan_rendering),
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
                await planning_run_repo.update_planning_run_progress(
                    db, run_id, step_name,
                    json.dumps({"completed_steps": completed_steps, "last_step": step_name}),
                )
            except Exception as exc:
                logger.warning("Progress checkpoint failed: %s", exc)

        # HITL gate: plan_approval after plan_rendering
        try:
            from maelstrom.services.policy_service import get_policy_config
            from maelstrom.services.hitl_manager import get_hitl_manager
            policy = await get_policy_config(db, session_id)
            if policy.plan_approval:
                await _emit("approval_pending", {"type": "plan_approval"})
                manager = get_hitl_manager()
                decision = await manager.request_approval(
                    db, session_id, run_id, "plan_approval",
                    {"hypothesis": state.get("hypothesis", ""), "plan_summary": str(state.get("plan", {}))[:500]},
                )
                if decision == "rejected":
                    raise RuntimeError("Plan rejected by reviewer")
        except RuntimeError:
            raise
        except Exception as e:
            logger.warning("HITL gate skipped: %s", e)

        # Persist result
        result = {
            "plan": state.get("plan"),
            "hypothesis": state.get("hypothesis", ""),
            "variables": state.get("variables", []),
            "baselines": state.get("baselines"),
            "ablation": state.get("ablation"),
            "dataset_protocol": state.get("dataset_protocol"),
            "metrics": state.get("metrics", []),
            "checklist": state.get("checklist"),
            "risk_memo": state.get("risk_memo"),
            "validation": state.get("validation"),
        }
        await planning_run_repo.update_planning_run_result(db, run_id, json.dumps(result, default=str))
        await planning_run_repo.update_planning_run_status(db, run_id, "completed")
        _run_state[run_id]["current_step"] = "completed"
        _run_state[run_id]["result"] = result
        await _emit("run_completed", {"engine": "planning", "run_id": run_id})

        # Advance session phase
        try:
            from maelstrom.services.phase_tracker import advance_phase_on_completion
            from maelstrom.services.policy_service import get_policy_config as _get_policy
            _policy = await _get_policy(db, session_id)
            if _policy.auto_advance_phase:
                await advance_phase_on_completion(session_id, "planning")
        except Exception as e:
            logger.warning("Phase advance failed: %s", e)

        # Persist ExperimentPlan artifact
        try:
            from maelstrom.db import artifact_repo, session_repo
            plan = state.get("plan")
            if plan:
                await artifact_repo.create_artifact(db, session_id, "experiment_plan", json.dumps(plan, default=str))
                await _emit("artifact_created", {"artifact_type": "experiment_plan", "session_id": session_id})
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
            await mem.ingest_text(
                session_id, "planning", run_id,
                f"ExperimentPlan: {state.get('hypothesis', '')}",
                json.dumps(result.get("plan", {}), default=str, ensure_ascii=False)[:3000],
            )
        except Exception as e:
            logger.warning("EvidenceMemory writeback failed: %s", e)

        # Write evidence edges: plan → addresses → gap
        try:
            from maelstrom.db import evidence_edge_repo
            plan_data = state.get("plan", {})
            if isinstance(plan_data, dict):
                for gap_ref in plan_data.get("addressed_gaps", plan_data.get("gap_ids", [])):
                    gap_id = gap_ref if isinstance(gap_ref, str) else gap_ref.get("gap_id", "")
                    if gap_id:
                        await evidence_edge_repo.create_edge(db, run_id, "experiment_plan", gap_id, "gap_item", "addresses")
        except Exception as e:
            logger.warning("Evidence edge writeback failed: %s", e)

        # Update session phase
        try:
            from maelstrom.services.phase_tracker import _set_phase
            from maelstrom.schemas.common import ResearchPhase
            await _set_phase(db, session_id, ResearchPhase.planning)
        except Exception as e:
            logger.warning("Phase update failed: %s", e)

        await _emit("result", result)
        await _emit("__done__", {})

    except Exception as e:
        logger.exception("Planning run %s failed: %s", run_id, e)
        await planning_run_repo.update_planning_run_status(db, run_id, "failed")
        _run_state[run_id]["current_step"] = "failed"
        _run_state[run_id]["error"] = str(e)
        await _emit("run_failed", {"engine": "planning", "run_id": run_id, "error": str(e)})
        await _emit("error", {"message": str(e), "step": _run_state[run_id].get("current_step", "unknown")})
        await _emit("__done__", {})
