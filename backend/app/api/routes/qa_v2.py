from __future__ import annotations

import asyncio
import importlib
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.translation_store import get_translation_store

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 导入 QA 核心模块
from agent.core.types import (
    global_trace_store,
    TraceContext,
    RouteType,
    EvidencePack,
    Citation,
)
from agent.core.qa_memory import qa_session_memory
from agent.core.qa_metrics import qa_metrics

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent/qa/v2", tags=["qa-v2"])


class QARequest(BaseModel):
    query: str
    docId: Optional[str] = None
    sessionId: Optional[str] = None
    options: Optional[Dict[str, Any]] = None


class Citation(BaseModel):
    chunkId: str
    text: str
    score: float


class QAResponse(BaseModel):
    answer: str
    citations: List[Citation] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    route: str
    traceId: str
    contextBlocks: List[Dict[str, Any]] = Field(default_factory=list)


_trace_store: Dict[str, Dict[str, Any]] = {}
_runtime: Dict[str, Any] = {}


def _deps() -> Dict[str, Any]:
    if _runtime:
        return _runtime

    prompt_module = importlib.import_module("agent.agents.prompt_agent_v2")
    plan_module = importlib.import_module("agent.agents.plan_agent_v2")
    writing_module = importlib.import_module("agent.agents.writing_agent_v2")
    verifier_module = importlib.import_module("agent.agents.verifier_agent_v2")
    types_module = importlib.import_module("agent.core.types")
    memory_module = importlib.import_module("agent.core.qa_memory")
    metrics_module = importlib.import_module("agent.core.qa_metrics")
    doc_tool_module = importlib.import_module("agent.tools.doc_search_tool")

    _runtime.update(
        {
            "prompt_agent": prompt_module.PromptAgentV2(),
            "plan_agent": plan_module.PlanAgentV2(),
            "writing_agent": writing_module.WritingAgentV2(),
            "verifier_agent": verifier_module.VerifierAgentV2(),
            "DAGExecutor": types_module.DAGExecutor,
            "EvidencePack": types_module.EvidencePack,
            "RouteType": types_module.RouteType,
            "TraceContext": types_module.TraceContext,
            "CoreCitation": types_module.Citation,
            "global_trace_store": types_module.global_trace_store,
            "memory": memory_module.qa_session_memory,
            "metrics": metrics_module.qa_metrics,
            "doc_search_tool": doc_tool_module.DocSearchTool(),
            "indexed_docs": set(),
        }
    )
    return _runtime


def _coerce_route(value: Any) -> Any:
    route_type = _deps()["RouteType"]
    if isinstance(value, route_type):
        return value
    try:
        return route_type(str(value))
    except ValueError:
        return route_type.DOC_GROUNDED


def _safe_float(value: Any, default: float, low: float, high: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))


def _safe_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))


def _to_api_citations(citations: List[Any]) -> List[Citation]:
    return [
        Citation(
            chunkId=str(getattr(citation, "chunk_id", "unknown")),
            text=str(getattr(citation, "text", "")),
            score=float(getattr(citation, "score", 0.0)),
        )
        for citation in citations
    ]


async def _search_chunks(
    query: str,
    doc_id: Optional[str],
    top_k: int,
    trace_ctx: Any,
) -> List[Dict[str, Any]]:
    if doc_id:
        await _ensure_doc_indexed(doc_id=doc_id, trace_ctx=trace_ctx)

    trace_ctx.log_event(
        "retrieve_start",
        {"query": query, "doc_id": doc_id, "top_k": top_k},
    )
    result = await _deps()["doc_search_tool"].execute(
        action="search",
        query=query,
        top_k=top_k,
        doc_id=doc_id,
    )
    if not result.success:
        trace_ctx.log_event(
            "retrieve_failed",
            {"error": result.error, "recoverable": result.recoverable},
        )
        if result.recoverable:
            return []
        raise ValueError(result.error or "DocSearchTool failed")

    chunks = list((result.data or {}).get("chunks", []))
    trace_ctx.log_event("retrieve_done", {"chunk_count": len(chunks)})
    return chunks


async def _ensure_doc_indexed(doc_id: str, trace_ctx: Any) -> bool:
    indexed_docs = _deps().get("indexed_docs")
    if isinstance(indexed_docs, set) and doc_id in indexed_docs:
        return True

    store = get_translation_store()
    entry = await store.get_entry(doc_id)
    if not entry:
        trace_ctx.log_event("index_missing_entry", {"doc_id": doc_id})
        return False

    markdown = str(entry.get("markdown") or "").strip()
    ocr_markdown = str(entry.get("ocr_markdown") or "").strip()
    text = "\n\n".join([part for part in [markdown, ocr_markdown] if part])
    if not text:
        trace_ctx.log_event("index_empty_content", {"doc_id": doc_id})
        return False

    meta_raw = entry.get("meta")
    meta: Dict[str, Any] = meta_raw if isinstance(meta_raw, dict) else {}
    doc_name = str(meta.get("display_name") or meta.get("filename") or doc_id)

    result = await _deps()["doc_search_tool"].execute(
        action="index",
        doc_id=doc_id,
        markdown=text,
        doc_name=doc_name,
    )

    if not result.success:
        trace_ctx.log_event(
            "index_failed",
            {"doc_id": doc_id, "error": result.error, "recoverable": result.recoverable},
        )
        return False

    if isinstance(indexed_docs, set):
        indexed_docs.add(doc_id)
    trace_ctx.log_event("index_ready", {"doc_id": doc_id, "doc_name": doc_name})
    return True


def _build_evidence(chunks: List[Dict[str, Any]], budget_chars: int) -> Any:
    kept: List[Dict[str, Any]] = []
    used = 0
    for chunk in chunks:
        text = str(chunk.get("text") or "")
        if not text:
            continue
        remaining = budget_chars - used
        if remaining <= 0:
            break
        trimmed = text[:remaining]
        kept.append(
            {
                "text": trimmed,
                "source": chunk.get("source") or chunk.get("chunk_id") or "unknown",
                "score": float(chunk.get("score") or 0.0),
            }
        )
        used += len(trimmed)
    evidence_cls = _deps()["EvidencePack"]
    return evidence_cls(chunks=kept, metadata={"budget_chars": budget_chars, "used_chars": used})


async def _fallback_single_hop(
    query: str,
    doc_id: Optional[str],
    budget_chars: int,
    trace_ctx: Any,
) -> Dict[str, Any]:
    trace_ctx.log_event("fallback_start", {"query": query, "doc_id": doc_id})
    chunks = await _search_chunks(query=query, doc_id=doc_id, top_k=3, trace_ctx=trace_ctx)
    evidence = _build_evidence(chunks, budget_chars)
    route_type = _deps()["RouteType"]
    core_citation = _deps()["CoreCitation"]
    composed = await _deps()["writing_agent"].compose_answer(
        query=query,
        route=route_type.DOC_GROUNDED,
        evidence=evidence,
    )
    citations = composed.get("citations", [])
    if not citations and evidence.chunks:
        citations = [
            core_citation(
                chunk_id=str(chunk.get("source") or f"chunk_{idx + 1}"),
                text=str(chunk.get("text") or "")[:200],
                score=float(chunk.get("score") or 0.0),
            )
            for idx, chunk in enumerate(evidence.chunks[:3])
        ]
    trace_ctx.log_event("fallback_done", {"citation_count": len(citations)})
    return {
        "answer": str(composed.get("answer") or "未找到可用证据。"),
        "citations": citations,
        "confidence": float(composed.get("confidence") or 0.35),
        "route": route_type.DOC_GROUNDED,
        "context_blocks": [{"type": "fallback", "data": {"enabled": True}}],
    }


async def _run_pipeline(
    request: QARequest,
    trace_ctx: Any,
    budget_chars: int,
) -> Dict[str, Any]:
    route_type = _deps()["RouteType"]
    evidence_cls = _deps()["EvidencePack"]
    session_id = request.sessionId or "default"
    history = _deps()["memory"].get_context(session_id=session_id, doc_id=request.docId)

    prompt_result = await _deps()["prompt_agent"].process(
        query=request.query,
        doc_id=request.docId,
        trace_ctx=trace_ctx,
    )
    route = _coerce_route(prompt_result.get("route"))
    context_blocks = list(prompt_result.get("context_blocks", []))
    context_blocks.append(
        {
            "type": "session_history",
            "data": {"turn_count": len(history)},
        }
    )

    plan = await _deps()["plan_agent"].build_plan(query=request.query, route=route, doc_id=request.docId)
    trace_ctx.log_event("plan_built", {"plan_id": plan.plan_id, "node_count": len(plan.nodes)})

    executor = _deps()["DAGExecutor"]()

    async def retrieve_node() -> List[Dict[str, Any]]:
        return await _search_chunks(request.query, request.docId, 5, trace_ctx)

    async def retrieve_primary_node() -> List[Dict[str, Any]]:
        return await _search_chunks(request.query, request.docId, 5, trace_ctx)

    async def retrieve_secondary_node() -> List[Dict[str, Any]]:
        query = f"{request.query} 关键点"
        return await _search_chunks(query, request.docId, 3, trace_ctx)

    async def reason_node(
        retrieve_primary_result: List[Dict[str, Any]],
        retrieve_secondary_result: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merged = list(retrieve_primary_result) + list(retrieve_secondary_result)
        dedup: Dict[str, Dict[str, Any]] = {}
        for item in merged:
            key = str(item.get("source") or item.get("text") or id(item))
            if key not in dedup:
                dedup[key] = item
        return list(dedup.values())

    async def write_node(
        retrieve_result: Optional[List[Dict[str, Any]]] = None,
        reason_result: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if route == route_type.FAST_PATH:
            evidence = evidence_cls(chunks=[])
        elif route == route_type.MULTI_HOP:
            evidence = _build_evidence(reason_result or [], budget_chars)
        else:
            evidence = _build_evidence(retrieve_result or [], budget_chars)

        composed = await _deps()["writing_agent"].compose_answer(
            query=request.query,
            route=route,
            evidence=evidence,
        )
        composed["evidence"] = evidence
        return composed

    async def verify_node(write_result: Dict[str, Any]) -> Dict[str, Any]:
        evidence = write_result.get("evidence")
        if not isinstance(evidence, evidence_cls):
            evidence = evidence_cls(chunks=[])
        result = await _deps()["verifier_agent"].verify(
            route=route,
            answer=str(write_result.get("answer") or ""),
            citations=list(write_result.get("citations") or []),
            evidence=evidence,
        )
        return result

    node_funcs = {
        "retrieve": retrieve_node,
        "retrieve_primary": retrieve_primary_node,
        "retrieve_secondary": retrieve_secondary_node,
        "reason": reason_node,
        "write": write_node,
        "verify": verify_node,
    }

    for node in plan.nodes:
        node_func = node_funcs.get(node.node_id)
        if node_func is None:
            raise ValueError(f"Unknown node id: {node.node_id}")
        executor.add_node(
            node_id=node.node_id,
            func=node_func,
            dependencies=node.dependencies,
        )

    results = await executor.execute()
    write_result = results.get("write")
    verify_result = results.get("verify")

    if not isinstance(write_result, dict) or not isinstance(verify_result, dict):
        raise ValueError("pipeline missing write/verify result")

    if not bool(verify_result.get("passed")):
        _deps()["metrics"].record_verify_failed()
        reasons = verify_result.get("reasons") or []
        raise ValueError("verify failed: " + ", ".join(str(reason) for reason in reasons))

    return {
        "answer": str(verify_result.get("answer") or write_result.get("answer") or ""),
        "citations": list(verify_result.get("citations") or []),
        "confidence": float(write_result.get("confidence") or 0.5),
        "route": route,
        "context_blocks": context_blocks,
        "plan_id": plan.plan_id,
    }


@router.post("", response_model=QAResponse)
async def qa_v2_chat(qa_request: QARequest) -> QAResponse:
    trace_ctx = _deps()["TraceContext"]()
    options = qa_request.options or {}
    timeout_sec = _safe_float(options.get("timeout_sec"), default=8.0, low=1.0, high=30.0)
    budget_chars = _safe_int(options.get("max_context_chars"), default=6000, low=1000, high=30000)
    session_id = qa_request.sessionId or "default"

    trace_ctx.log_event(
        "request_received",
        {
            "query": qa_request.query,
            "doc_id": qa_request.docId,
            "session_id": session_id,
            "timeout_sec": timeout_sec,
            "budget_chars": budget_chars,
        },
    )

    _deps()["memory"].append(session_id, role="user", content=qa_request.query, doc_id=qa_request.docId)

    try:
        pipeline_result = await asyncio.wait_for(
            _run_pipeline(request=qa_request, trace_ctx=trace_ctx, budget_chars=budget_chars),
            timeout=timeout_sec,
        )
    except Exception as exc:
        logger.warning("qa_v2 pipeline failed, fallback enabled: %s", exc)
        _deps()["metrics"].record_fallback()
        pipeline_result = await _fallback_single_hop(
            query=qa_request.query,
            doc_id=qa_request.docId,
            budget_chars=budget_chars,
            trace_ctx=trace_ctx,
        )

    answer = str(pipeline_result.get("answer") or "")
    citations = list(pipeline_result.get("citations") or [])
    confidence = float(pipeline_result.get("confidence") or 0.0)
    route = _coerce_route(pipeline_result.get("route"))
    context_blocks = list(pipeline_result.get("context_blocks") or [])

    _deps()["memory"].append(session_id, role="assistant", content=answer, doc_id=qa_request.docId)

    trace_ctx.log_event(
        "response_sent",
        {
            "route": route.value,
            "citation_count": len(citations),
            "confidence": confidence,
            "duration_ms": trace_ctx.duration_ms,
        },
    )
    _deps()["metrics"].record_request(route=route.value, latency_ms=trace_ctx.duration_ms)

    _trace_store[trace_ctx.trace_id] = trace_ctx.to_dict()
    if len(_trace_store) > 200:
        oldest_trace_id = next(iter(_trace_store.keys()))
        _trace_store.pop(oldest_trace_id, None)

    return QAResponse(
        answer=answer,
        citations=_to_api_citations(citations),
        confidence=confidence,
        route=route.value,
        traceId=trace_ctx.trace_id,
        contextBlocks=context_blocks,
    )


@router.get("/health")
async def health_check() -> Dict[str, str]:
    return {
        "status": "healthy",
        "version": "2.1.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/trace/{trace_id}")
async def get_trace(trace_id: str) -> Dict[str, Any]:
    trace = _trace_store.get(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return trace


@router.get("/metrics")
async def get_metrics() -> Dict[str, object]:
    return _deps()["metrics"].snapshot()



# ========== 日志查询 API ==========


@router.get("/logs", response_model=Dict[str, Any])
async def get_logs(
    level: Optional[str] = None,
    event_type: Optional[str] = None,
    trace_id: Optional[str] = None,
    session_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """查询 QA 系统日志

    支持按级别、事件类型、trace_id、session_id 过滤
    """
    return global_trace_store.query(
        trace_id=trace_id,
        event_type=event_type,
        session_id=session_id,
        limit=limit,
        offset=offset,
    )



@router.get("/logs/trace/{trace_id}", response_model=Dict[str, Any])
async def get_trace_logs(
    trace_id: str,
) -> Dict[str, Any]:
    """获取特定 Trace ID 的所有日志"""
    trace_ctx = global_trace_store.get(trace_id)
    if not trace_ctx:
        return {
            "trace_id": trace_id,
            "logs": [],
            "analysis": {
                "message": f"Trace {trace_id} 未找到",
                "available_traces": list(global_trace_store._traces.keys())[-10:]  # 最近10个
            }
        }

    events = [
        {
            "timestamp": e.timestamp,
            "event_type": e.event_type,
            "data": e.data,
        }
        for e in trace_ctx.events
    ]

    return {
        "trace_id": trace_id,
        "start_time": trace_ctx.start_time.isoformat(),
        "duration_ms": trace_ctx.duration_ms,
        "event_count": len(events),
        "logs": events,
        "analysis": {
            "message": "Trace 分析功能已就绪",
            "route": next((e.data.get("route") for e in trace_ctx.events if e.event_type == "response_sent"), None),
        }
    }
