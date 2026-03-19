"""Evidence Graph schemas — edges, lineage, and structured graph responses."""
from __future__ import annotations

from pydantic import BaseModel


class EvidenceEdge(BaseModel):
    id: str = ""
    source_id: str
    source_type: str
    target_id: str
    target_type: str
    relation: str
    metadata_json: str = "{}"
    created_at: str = ""


class LineageNode(BaseModel):
    node_id: str
    node_type: str
    depth: int = 0


class LineageResponse(BaseModel):
    root_id: str
    edges: list[EvidenceEdge] = []
    nodes: list[LineageNode] = []


class GraphNode(BaseModel):
    """A node in the structured evidence graph."""
    node_id: str
    node_type: str  # paper, gap_item, claim, experiment_plan, experiment_run, conclusion, feasibility, review
    title: str = ""
    snippet: str = ""


class StructuredGraphResponse(BaseModel):
    """Full evidence graph for a session with typed nodes and edges."""
    session_id: str
    nodes: list[GraphNode] = []
    edges: list[EvidenceEdge] = []
    node_type_counts: dict[str, int] = {}


class SearchHit(BaseModel):
    evidence_id: str
    source_type: str
    source_id: str
    title: str
    snippet: str = ""
    rank: float = 0.0


class SearchResponse(BaseModel):
    session_id: str
    query: str
    hits: list[SearchHit] = []
    total: int = 0


class EdgeCreateRequest(BaseModel):
    source_id: str
    source_type: str
    target_id: str
    target_type: str
    relation: str
    metadata_json: str = "{}"


class SessionSummaryResponse(BaseModel):
    session_id: str
    paper_count: int = 0
    gap_count: int = 0
    claim_count: int = 0
    review_count: int = 0
    total_entries: int = 0
    edge_count: int = 0
