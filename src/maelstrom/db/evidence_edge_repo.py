"""Evidence edge repository — CRUD for evidence_edges table."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite


async def create_edge(
    db: aiosqlite.Connection,
    source_id: str,
    source_type: str,
    target_id: str,
    target_type: str,
    relation: str,
    metadata_json: str = "{}",
) -> dict:
    eid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO evidence_edges (id, source_id, source_type, target_id, target_type, relation, metadata_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (eid, source_id, source_type, target_id, target_type, relation, metadata_json, now),
    )
    await db.commit()
    return {
        "id": eid, "source_id": source_id, "source_type": source_type,
        "target_id": target_id, "target_type": target_type,
        "relation": relation, "metadata_json": metadata_json, "created_at": now,
    }


async def get_edges(
    db: aiosqlite.Connection, node_id: str, direction: str = "both",
) -> list[dict]:
    if direction == "outgoing":
        cur = await db.execute("SELECT * FROM evidence_edges WHERE source_id = ?", (node_id,))
    elif direction == "incoming":
        cur = await db.execute("SELECT * FROM evidence_edges WHERE target_id = ?", (node_id,))
    else:
        cur = await db.execute(
            "SELECT * FROM evidence_edges WHERE source_id = ? OR target_id = ?",
            (node_id, node_id),
        )
    return [dict(r) for r in await cur.fetchall()]


async def get_lineage(
    db: aiosqlite.Connection, node_id: str, max_depth: int = 3,
) -> list[dict]:
    """Recursive CTE traversal to collect lineage edges up to max_depth."""
    sql = """
        WITH RECURSIVE lineage(node, depth) AS (
            VALUES(?, 0)
            UNION
            SELECT CASE
                WHEN e.source_id = lineage.node THEN e.target_id
                ELSE e.source_id
            END, lineage.depth + 1
            FROM evidence_edges e
            JOIN lineage ON (e.source_id = lineage.node OR e.target_id = lineage.node)
            WHERE lineage.depth < ?
        )
        SELECT DISTINCT e.*
        FROM evidence_edges e
        JOIN lineage l ON (e.source_id = l.node OR e.target_id = l.node)
    """
    cur = await db.execute(sql, (node_id, max_depth))
    return [dict(r) for r in await cur.fetchall()]


async def list_by_session(
    db: aiosqlite.Connection, session_id: str,
) -> list[dict]:
    """List edges where source or target matches evidence_memory entries for a session."""
    cur = await db.execute(
        "SELECT e.* FROM evidence_edges e "
        "JOIN evidence_memory em ON (e.source_id = em.source_id OR e.target_id = em.source_id) "
        "WHERE em.session_id = ? "
        "GROUP BY e.id",
        (session_id,),
    )
    return [dict(r) for r in await cur.fetchall()]


async def count_by_session(db: aiosqlite.Connection, session_id: str) -> int:
    """Count edges scoped to a session."""
    cur = await db.execute(
        "SELECT COUNT(DISTINCT e.id) FROM evidence_edges e "
        "JOIN evidence_memory em ON (e.source_id = em.source_id OR e.target_id = em.source_id) "
        "WHERE em.session_id = ?",
        (session_id,),
    )
    row = await cur.fetchone()
    return row[0] if row else 0


async def get_structured_graph(
    db: aiosqlite.Connection, session_id: str,
) -> dict:
    """Build a structured graph with typed nodes and edges for a session.

    Returns {nodes: [{node_id, node_type, title, snippet}], edges: [...], node_type_counts: {...}}
    """
    # Get all evidence memory entries for the session (these are our nodes)
    cur = await db.execute(
        "SELECT source_id, source_type, title, substr(content, 1, 200) as snippet "
        "FROM evidence_memory WHERE session_id = ?",
        (session_id,),
    )
    mem_rows = await cur.fetchall()

    nodes: dict[str, dict] = {}
    for row in mem_rows:
        nid = row[0]  # source_id
        nodes[nid] = {
            "node_id": nid,
            "node_type": row[1],
            "title": row[2],
            "snippet": row[3] or "",
        }

    # Get all edges scoped to this session
    edges = await list_by_session(db, session_id)

    # Add any nodes referenced in edges but not in evidence_memory
    for e in edges:
        for side in ("source", "target"):
            nid = e[f"{side}_id"]
            if nid not in nodes:
                nodes[nid] = {
                    "node_id": nid,
                    "node_type": e[f"{side}_type"],
                    "title": "",
                    "snippet": "",
                }

    # Count by type
    type_counts: dict[str, int] = {}
    for n in nodes.values():
        t = n["node_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "node_type_counts": type_counts,
    }
