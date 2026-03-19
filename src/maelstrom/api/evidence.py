"""Evidence Graph API — search, graph edges, lineage, and structured queries."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from maelstrom.db import evidence_edge_repo
from maelstrom.db.database import get_db
from maelstrom.schemas.evidence_graph import (
    EdgeCreateRequest,
    EvidenceEdge,
    LineageResponse,
    SearchResponse,
    SessionSummaryResponse,
    StructuredGraphResponse,
)
from maelstrom.services.evidence_memory import get_evidence_memory

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


# ── FTS Search ────────────────────────────────────────────────────────


@router.get("/search", response_model=SearchResponse)
async def search_evidence(session_id: str, query: str, limit: int = 10):
    """Full-text search across session evidence memory."""
    mem = get_evidence_memory()
    hits = await mem.search(session_id, query, limit=limit)
    return SearchResponse(
        session_id=session_id,
        query=query,
        hits=[h.model_dump() for h in hits],
        total=len(hits),
    )


# ── Session Summary ───────────────────────────────────────────────────


@router.get("/summary", response_model=SessionSummaryResponse)
async def get_summary(session_id: str):
    """Get evidence memory summary with counts by type and edge count."""
    mem = get_evidence_memory()
    summary = await mem.get_session_summary(session_id)
    db = await get_db()
    edge_count = await evidence_edge_repo.count_by_session(db, session_id)
    return SessionSummaryResponse(
        session_id=session_id,
        paper_count=summary.paper_count,
        gap_count=summary.gap_count,
        claim_count=getattr(summary, "claim_count", 0),
        review_count=getattr(summary, "review_count", 0),
        total_entries=summary.total_entries,
        edge_count=edge_count,
    )


# ── Structured Graph ──────────────────────────────────────────────────


@router.get("/graph", response_model=StructuredGraphResponse)
async def get_graph(session_id: str):
    """Get the full structured evidence graph for a session.

    Returns typed nodes (paper, gap_item, claim, experiment_plan, conclusion, ...)
    and edges (supported_by, extracted_from, addresses, inferred_from, ...).
    """
    db = await get_db()
    result = await evidence_edge_repo.get_structured_graph(db, session_id)
    return StructuredGraphResponse(
        session_id=session_id,
        nodes=result["nodes"],
        edges=result["edges"],
        node_type_counts=result["node_type_counts"],
    )


# ── Node Edges ────────────────────────────────────────────────────────


@router.get("/nodes/{node_id}/edges")
async def get_node_edges(node_id: str, direction: str = "both"):
    """Get all edges connected to a specific node."""
    if direction not in ("both", "incoming", "outgoing"):
        raise HTTPException(status_code=400, detail="direction must be 'both', 'incoming', or 'outgoing'")
    db = await get_db()
    edges = await evidence_edge_repo.get_edges(db, node_id, direction=direction)
    return {"node_id": node_id, "direction": direction, "edges": edges}


# ── Lineage ───────────────────────────────────────────────────────────


@router.get("/lineage/{node_id}", response_model=LineageResponse)
async def get_lineage(node_id: str, max_depth: int = 3):
    """Recursive lineage traversal from a node (SQL CTE)."""
    db = await get_db()
    edges = await evidence_edge_repo.get_lineage(db, node_id, max_depth=max_depth)
    # Collect unique nodes with depth info
    nodes: dict[str, dict] = {}
    for e in edges:
        for side in ("source", "target"):
            nid = e[f"{side}_id"]
            if nid not in nodes:
                nodes[nid] = {"node_id": nid, "node_type": e[f"{side}_type"], "depth": 0}
    # Approximate depth from root
    if node_id in nodes:
        nodes[node_id]["depth"] = 0
    return LineageResponse(
        root_id=node_id,
        edges=[EvidenceEdge(**e) for e in edges],
        nodes=[{"node_id": n["node_id"], "node_type": n["node_type"], "depth": n["depth"]} for n in nodes.values()],
    )


# ── Edge CRUD ─────────────────────────────────────────────────────────


@router.post("/edges", status_code=201)
async def create_edge(body: EdgeCreateRequest):
    """Create a new evidence edge."""
    db = await get_db()
    edge = await evidence_edge_repo.create_edge(
        db,
        body.source_id, body.source_type,
        body.target_id, body.target_type,
        body.relation, body.metadata_json,
    )
    return edge
