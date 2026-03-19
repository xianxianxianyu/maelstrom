"""EvidenceMemory — abstract base + SQLite FTS5 implementation."""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import aiosqlite
from pydantic import BaseModel, Field

from maelstrom.db.database import get_db
from maelstrom.schemas.gap import GapItem
from maelstrom.schemas.paper import PaperRecord


# ── Result models ────────────────────────────────────────────────────


class EvidenceHit(BaseModel):
    evidence_id: str
    source_type: str
    source_id: str
    title: str
    snippet: str = ""
    rank: float = 0.0


class SessionMemorySummary(BaseModel):
    session_id: str
    paper_count: int = 0
    gap_count: int = 0
    chat_count: int = 0
    total_entries: int = 0


# ── Abstract base ────────────────────────────────────────────────────


class EvidenceMemoryBase(ABC):
    @abstractmethod
    async def ingest_paper(self, session_id: str, paper: PaperRecord) -> str: ...

    @abstractmethod
    async def ingest_gap(self, session_id: str, gap: GapItem) -> str: ...

    @abstractmethod
    async def ingest_text(
        self, session_id: str, source_type: str, source_id: str, title: str, content: str,
    ) -> str: ...

    @abstractmethod
    async def search(self, session_id: str, query: str, limit: int = 10) -> list[EvidenceHit]: ...

    @abstractmethod
    async def search_by_source_id(self, session_id: str, source_id: str) -> list[EvidenceHit]: ...

    @abstractmethod
    async def get_session_summary(self, session_id: str) -> SessionMemorySummary: ...

    # ── Evidence Graph extensions ────────────────────────────────────

    async def add_edge(
        self, source_id: str, source_type: str, target_id: str, target_type: str, relation: str,
    ) -> str:
        """Add an evidence edge. Default no-op for non-graph implementations."""
        return ""

    async def get_edges(self, node_id: str, direction: str = "both") -> list[dict]:
        return []

    async def get_lineage(self, node_id: str, max_depth: int = 3) -> list[dict]:
        return []


# ── SQLite FTS5 implementation ───────────────────────────────────────


class SqliteEvidenceMemory(EvidenceMemoryBase):
    def __init__(self, db: aiosqlite.Connection | None = None):
        self._db = db

    async def _get_db(self) -> aiosqlite.Connection:
        if self._db is not None:
            return self._db
        return await get_db()

    async def ingest_paper(self, session_id: str, paper: PaperRecord) -> str:
        authors_str = ", ".join(a.name for a in paper.authors) if paper.authors else ""
        content = f"{paper.abstract or ''}\n{authors_str}"
        return await self.ingest_text(
            session_id, "paper", paper.paper_id, paper.title, content,
        )

    async def ingest_gap(self, session_id: str, gap: GapItem) -> str:
        content = f"{gap.summary}\nType: {', '.join(gap.gap_type)}"
        return await self.ingest_text(
            session_id, "gap", gap.gap_id, gap.title, content,
        )

    async def ingest_text(
        self, session_id: str, source_type: str, source_id: str, title: str, content: str,
    ) -> str:
        db = await self._get_db()
        eid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO evidence_memory (id, session_id, source_type, source_id, title, content, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (eid, session_id, source_type, source_id, title, content, now),
        )
        await db.commit()
        return eid

    async def search(self, session_id: str, query: str, limit: int = 10) -> list[EvidenceHit]:
        db = await self._get_db()
        # Escape FTS5 special characters in query
        safe_query = _escape_fts_query(query)
        if not safe_query:
            return []

        sql = """
            SELECT em.id, em.source_type, em.source_id, em.title,
                   snippet(evidence_memory_fts, 1, '<b>', '</b>', '...', 32) as snippet,
                   bm25(evidence_memory_fts) as rank
            FROM evidence_memory_fts
            JOIN evidence_memory em ON evidence_memory_fts.rowid = em.rowid
            WHERE evidence_memory_fts MATCH ? AND em.session_id = ?
            ORDER BY rank
            LIMIT ?
        """
        try:
            cursor = await db.execute(sql, (safe_query, session_id, limit))
            rows = await cursor.fetchall()
        except Exception:
            return []

        results = []
        for row in rows:
            results.append(EvidenceHit(
                evidence_id=row[0],
                source_type=row[1],
                source_id=row[2],
                title=row[3],
                snippet=row[4] or "",
                rank=float(row[5]) if row[5] else 0.0,
            ))
        return results

    async def search_by_source_id(self, session_id: str, source_id: str) -> list[EvidenceHit]:
        db = await self._get_db()
        cursor = await db.execute(
            "SELECT id, source_type, source_id, title, content FROM evidence_memory "
            "WHERE session_id = ? AND source_id = ?",
            (session_id, source_id),
        )
        rows = await cursor.fetchall()
        return [
            EvidenceHit(
                evidence_id=row[0],
                source_type=row[1],
                source_id=row[2],
                title=row[3],
                snippet=row[4][:200] if row[4] else "",
                rank=1.0,
            )
            for row in rows
        ]

    async def get_session_summary(self, session_id: str) -> SessionMemorySummary:
        db = await self._get_db()
        cursor = await db.execute(
            "SELECT source_type, COUNT(*) FROM evidence_memory WHERE session_id = ? GROUP BY source_type",
            (session_id,),
        )
        rows = await cursor.fetchall()
        counts = {row[0]: row[1] for row in rows}
        total = sum(counts.values())
        return SessionMemorySummary(
            session_id=session_id,
            paper_count=counts.get("paper", 0),
            gap_count=counts.get("gap", 0),
            chat_count=counts.get("chat", 0),
            total_entries=total,
        )

    # ── Evidence Graph extensions ────────────────────────────────────

    async def add_edge(
        self, source_id: str, source_type: str, target_id: str, target_type: str, relation: str,
    ) -> str:
        from maelstrom.db import evidence_edge_repo
        db = await self._get_db()
        edge = await evidence_edge_repo.create_edge(db, source_id, source_type, target_id, target_type, relation)
        return edge["id"]

    async def get_edges(self, node_id: str, direction: str = "both") -> list[dict]:
        from maelstrom.db import evidence_edge_repo
        db = await self._get_db()
        return await evidence_edge_repo.get_edges(db, node_id, direction)

    async def get_lineage(self, node_id: str, max_depth: int = 3) -> list[dict]:
        from maelstrom.db import evidence_edge_repo
        db = await self._get_db()
        return await evidence_edge_repo.get_lineage(db, node_id, max_depth)


def _escape_fts_query(query: str) -> str:
    """Escape a user query for FTS5 MATCH.

    Wraps each token in double quotes to treat them as literals,
    avoiding FTS5 syntax errors from special characters.
    """
    tokens = query.strip().split()
    if not tokens:
        return ""
    # Quote each token and join with implicit AND
    escaped = " ".join(f'"{t}"' for t in tokens if t)
    return escaped


# ── Singleton ────────────────────────────────────────────────────────

_instance: SqliteEvidenceMemory | None = None


def get_evidence_memory() -> SqliteEvidenceMemory:
    global _instance
    if _instance is None:
        _instance = SqliteEvidenceMemory()
    return _instance


def set_evidence_memory(mem: SqliteEvidenceMemory) -> None:
    global _instance
    _instance = mem
