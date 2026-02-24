"""PaperRepository — 论文元数据 SQLite 存储层

提供论文结构化元数据的持久化存储，支持全文搜索（FTS5）和按领域/年份检索。
供 IndexAgent 写入，供 RAG / Context Engineering 检索。

Requirements: 6.1
"""

from __future__ import annotations

import json
import logging
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

# 默认数据库路径
_DEFAULT_DB_DIR = Path(__file__).resolve().parents[2] / "data"
_DEFAULT_DB_PATH = _DEFAULT_DB_DIR / "papers.db"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    title_zh TEXT NOT NULL DEFAULT '',
    authors TEXT NOT NULL DEFAULT '[]',
    abstract TEXT NOT NULL DEFAULT '',
    domain TEXT NOT NULL DEFAULT '',
    research_problem TEXT NOT NULL DEFAULT '',
    methodology TEXT NOT NULL DEFAULT '',
    contributions TEXT NOT NULL DEFAULT '[]',
    keywords TEXT NOT NULL DEFAULT '[]',
    tags TEXT NOT NULL DEFAULT '[]',
    base_models TEXT NOT NULL DEFAULT '[]',
    year INTEGER,
    venue TEXT NOT NULL DEFAULT '',
    embedding BLOB,
    quality_score INTEGER,
    filename TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_papers_domain ON papers(domain);
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
CREATE INDEX IF NOT EXISTS idx_papers_filename ON papers(filename);
"""

_FTS_SCHEMA_SQL = """\
CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
    title, title_zh, abstract, research_problem, methodology, keywords,
    content='papers', content_rowid='rowid'
);
"""

# FTS 同步触发器
_FTS_TRIGGERS_SQL = """\
CREATE TRIGGER IF NOT EXISTS papers_ai AFTER INSERT ON papers BEGIN
    INSERT INTO papers_fts(rowid, title, title_zh, abstract, research_problem, methodology, keywords)
    VALUES (new.rowid, new.title, new.title_zh, new.abstract, new.research_problem, new.methodology, new.keywords);
END;

CREATE TRIGGER IF NOT EXISTS papers_ad AFTER DELETE ON papers BEGIN
    INSERT INTO papers_fts(papers_fts, rowid, title, title_zh, abstract, research_problem, methodology, keywords)
    VALUES ('delete', old.rowid, old.title, old.title_zh, old.abstract, old.research_problem, old.methodology, old.keywords);
END;

CREATE TRIGGER IF NOT EXISTS papers_au AFTER UPDATE ON papers BEGIN
    INSERT INTO papers_fts(papers_fts, rowid, title, title_zh, abstract, research_problem, methodology, keywords)
    VALUES ('delete', old.rowid, old.title, old.title_zh, old.abstract, old.research_problem, old.methodology, old.keywords);
    INSERT INTO papers_fts(rowid, title, title_zh, abstract, research_problem, methodology, keywords)
    VALUES (new.rowid, new.title, new.title_zh, new.abstract, new.research_problem, new.methodology, new.keywords);
END;
"""


# ---------------------------------------------------------------------------
# PaperMetadata dataclass
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field as dc_field


@dataclass
class PaperMetadata:
    """论文结构化元数据"""

    title: str = ""
    title_zh: str = ""
    authors: list[str] = dc_field(default_factory=list)
    abstract: str = ""
    domain: str = ""
    research_problem: str = ""
    methodology: str = ""
    contributions: list[str] = dc_field(default_factory=list)
    keywords: list[str] = dc_field(default_factory=list)
    tags: list[str] = dc_field(default_factory=list)
    base_models: list[str] = dc_field(default_factory=list)
    year: int | None = None
    venue: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "title_zh": self.title_zh,
            "authors": self.authors,
            "abstract": self.abstract,
            "domain": self.domain,
            "research_problem": self.research_problem,
            "methodology": self.methodology,
            "contributions": self.contributions,
            "keywords": self.keywords,
            "tags": self.tags,
            "base_models": self.base_models,
            "year": self.year,
            "venue": self.venue,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PaperMetadata:
        return cls(
            title=data.get("title", ""),
            title_zh=data.get("title_zh", ""),
            authors=data.get("authors", []),
            abstract=data.get("abstract", ""),
            domain=data.get("domain", ""),
            research_problem=data.get("research_problem", ""),
            methodology=data.get("methodology", ""),
            contributions=data.get("contributions", []),
            keywords=data.get("keywords", []),
            tags=data.get("tags", []),
            base_models=data.get("base_models", []),
            year=data.get("year"),
            venue=data.get("venue", ""),
        )


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

def pack_embedding(vec: list[float]) -> bytes:
    """将 float 列表打包为 bytes（little-endian float32）"""
    return struct.pack(f"<{len(vec)}f", *vec)


def unpack_embedding(blob: bytes) -> list[float]:
    """从 bytes 解包为 float 列表"""
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


# ---------------------------------------------------------------------------
# PaperRepository
# ---------------------------------------------------------------------------

class PaperRepository:
    """论文元数据 SQLite 存储

    Usage::

        repo = PaperRepository()          # 使用默认路径
        await repo.init_db()              # 创建表（幂等）
        await repo.upsert("abc123", metadata, embedding, 85, "paper.pdf")
        results = await repo.search_text("transformer attention")
        await repo.close()
    """

    _JSON_FIELDS = ("authors", "contributions", "keywords", "tags", "base_models")
    _EDITABLE_FIELDS = {
        "title",
        "title_zh",
        "authors",
        "abstract",
        "domain",
        "research_problem",
        "methodology",
        "contributions",
        "keywords",
        "tags",
        "base_models",
        "year",
        "venue",
        "quality_score",
        "filename",
    }
    _MIGRATION_COLUMNS = {
        "tags": "TEXT NOT NULL DEFAULT '[]'",
    }

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self._db: aiosqlite.Connection | None = None

    async def init_db(self) -> None:
        """初始化数据库连接并创建表（幂等）"""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._db_path))
        self._db.row_factory = aiosqlite.Row

        await self._db.executescript(_SCHEMA_SQL)
        await self._db.executescript(_FTS_SCHEMA_SQL)
        await self._db.executescript(_FTS_TRIGGERS_SQL)
        await self._ensure_columns()
        await self._db.commit()
        logger.info("PaperRepository initialized: %s", self._db_path)

    async def _ensure_columns(self) -> None:
        db = self._ensure_db()
        cursor = await db.execute("PRAGMA table_info(papers)")
        rows = await cursor.fetchall()
        existing = {row[1] for row in rows}

        for column, sql_def in self._MIGRATION_COLUMNS.items():
            if column in existing:
                continue
            await db.execute(f"ALTER TABLE papers ADD COLUMN {column} {sql_def}")

    async def close(self) -> None:
        """关闭数据库连接"""
        if self._db:
            await self._db.close()
            self._db = None

    def _ensure_db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")
        return self._db

    # ── 写入 ──

    async def upsert(
        self,
        paper_id: str,
        metadata: PaperMetadata,
        embedding: list[float] | None = None,
        quality_score: int | None = None,
        filename: str = "",
    ) -> None:
        """插入或更新论文元数据"""
        db = self._ensure_db()

        emb_blob = pack_embedding(embedding) if embedding else None
        now = datetime.now(timezone.utc).isoformat()

        await db.execute(
            """\
            INSERT INTO papers (
                id, title, title_zh, authors, abstract, domain,
                research_problem, methodology, contributions, keywords, tags,
                base_models, year, venue, embedding, quality_score,
                filename, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                title_zh=excluded.title_zh,
                authors=excluded.authors,
                abstract=excluded.abstract,
                domain=excluded.domain,
                research_problem=excluded.research_problem,
                methodology=excluded.methodology,
                contributions=excluded.contributions,
                keywords=excluded.keywords,
                tags=excluded.tags,
                base_models=excluded.base_models,
                year=excluded.year,
                venue=excluded.venue,
                embedding=excluded.embedding,
                quality_score=excluded.quality_score,
                filename=excluded.filename,
                created_at=excluded.created_at
            """,
            (
                paper_id,
                metadata.title,
                metadata.title_zh,
                json.dumps(metadata.authors, ensure_ascii=False),
                metadata.abstract,
                metadata.domain,
                metadata.research_problem,
                metadata.methodology,
                json.dumps(metadata.contributions, ensure_ascii=False),
                json.dumps(metadata.keywords, ensure_ascii=False),
                json.dumps(metadata.tags, ensure_ascii=False),
                json.dumps(metadata.base_models, ensure_ascii=False),
                metadata.year,
                metadata.venue,
                emb_blob,
                quality_score,
                filename,
                now,
            ),
        )
        await db.commit()
        logger.info("Paper upserted: id=%s, title=%s", paper_id, metadata.title)

    # ── 查询 ──

    async def get_by_id(self, paper_id: str) -> dict | None:
        """按 ID 获取论文"""
        db = self._ensure_db()
        cursor = await db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
        row = await cursor.fetchone()
        return self._row_to_dict(row) if row else None

    async def get_many_by_ids(self, paper_ids: list[str]) -> dict[str, dict]:
        if not paper_ids:
            return {}

        db = self._ensure_db()
        placeholders = ",".join(["?"] * len(paper_ids))
        cursor = await db.execute(
            f"SELECT * FROM papers WHERE id IN ({placeholders})",
            tuple(paper_ids),
        )
        rows = await cursor.fetchall()
        result: dict[str, dict] = {}
        for row in rows:
            data = self._row_to_dict(row)
            result[data["id"]] = data
        return result

    async def list_for_history(
        self,
        query: str = "",
        tag: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        db = self._ensure_db()

        clauses: list[str] = []
        params: list[object] = []

        if query:
            like = f"%{query}%"
            clauses.append(
                "(title LIKE ? OR title_zh LIKE ? OR abstract LIKE ? OR domain LIKE ? OR filename LIKE ?)"
            )
            params.extend([like, like, like, like, like])

        if tag:
            like_tag = f"%{tag}%"
            clauses.append("(tags LIKE ? OR keywords LIKE ? OR domain LIKE ?)")
            params.extend([like_tag, like_tag, like_tag])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"SELECT * FROM papers {where} "
            "ORDER BY created_at DESC "
            "LIMIT ? OFFSET ?"
        )
        params.extend([max(1, min(limit, 200)), max(0, offset)])

        cursor = await db.execute(sql, tuple(params))
        rows = await cursor.fetchall()
        return [self._row_to_dict(r) for r in rows]

    async def update_partial(self, paper_id: str, updates: dict[str, object]) -> dict | None:
        db = self._ensure_db()

        sanitized: dict[str, object] = {}
        for key, value in updates.items():
            if key not in self._EDITABLE_FIELDS:
                continue
            sanitized[key] = self._normalize_update_value(key, value)

        if not sanitized:
            return await self.get_by_id(paper_id)

        set_clause = ", ".join([f"{k} = ?" for k in sanitized])
        await db.execute(
            f"UPDATE papers SET {set_clause}, created_at = ? WHERE id = ?",
            tuple(list(sanitized.values()) + [datetime.now(timezone.utc).isoformat(), paper_id]),
        )
        await db.commit()
        return await self.get_by_id(paper_id)

    @classmethod
    def _normalize_update_value(cls, key: str, value: object) -> object:
        if key in cls._JSON_FIELDS:
            if isinstance(value, str):
                value = [v.strip() for v in value.splitlines() if v.strip()]
            if isinstance(value, tuple):
                value = list(value)
            if not isinstance(value, list):
                value = []
            return json.dumps([str(v).strip() for v in value if str(v).strip()], ensure_ascii=False)

        if key in {"year", "quality_score"}:
            if value in (None, ""):
                return None
            try:
                return int(str(value))
            except (TypeError, ValueError):
                return None

        if value is None:
            return ""
        return str(value)

    async def search_text(self, query: str, limit: int = 20) -> list[dict]:
        """FTS5 全文搜索（中英文）"""
        db = self._ensure_db()
        cursor = await db.execute(
            """\
            SELECT p.* FROM papers p
            JOIN papers_fts f ON p.rowid = f.rowid
            WHERE papers_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        )
        rows = await cursor.fetchall()
        return [self._row_to_dict(r) for r in rows]

    async def search_by_domain(self, domain: str, limit: int = 50) -> list[dict]:
        """按领域检索"""
        db = self._ensure_db()
        cursor = await db.execute(
            "SELECT * FROM papers WHERE domain LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{domain}%", limit),
        )
        rows = await cursor.fetchall()
        return [self._row_to_dict(r) for r in rows]

    async def search_by_keywords(self, keywords: list[str], limit: int = 20) -> list[dict]:
        """按关键词检索（keywords JSON 数组中包含任一关键词）"""
        db = self._ensure_db()
        conditions = " OR ".join(["keywords LIKE ?"] * len(keywords))
        params = [f"%{kw}%" for kw in keywords] + [limit]
        cursor = await db.execute(
            f"SELECT * FROM papers WHERE ({conditions}) ORDER BY created_at DESC LIMIT ?",
            params,
        )
        rows = await cursor.fetchall()
        return [self._row_to_dict(r) for r in rows]

    async def list_all(self, limit: int = 100) -> list[dict]:
        """列出所有论文（最新在前）"""
        db = self._ensure_db()
        cursor = await db.execute(
            "SELECT * FROM papers ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [self._row_to_dict(r) for r in rows]

    async def delete(self, paper_id: str) -> bool:
        """删除论文"""
        db = self._ensure_db()
        cursor = await db.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
        await db.commit()
        return cursor.rowcount > 0

    async def count(self) -> int:
        """论文总数"""
        db = self._ensure_db()
        cursor = await db.execute("SELECT COUNT(*) FROM papers")
        row = await cursor.fetchone()
        return row[0] if row else 0

    # ── 内部方法 ──

    @staticmethod
    def _row_to_dict(row: aiosqlite.Row) -> dict:
        """将 Row 转为 dict，JSON 字段自动解析"""
        d = dict(row)
        for json_field in ("authors", "contributions", "keywords", "tags", "base_models"):
            if json_field in d and isinstance(d[json_field], str):
                try:
                    d[json_field] = json.loads(d[json_field])
                except (json.JSONDecodeError, TypeError):
                    d[json_field] = []
        # embedding 保持 blob 或 None
        if d.get("embedding"):
            d["embedding"] = unpack_embedding(d["embedding"])
        return d
