from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from .models import ClarificationThread, DialogueTurn, utc_now_iso


class SessionSQLiteStore:
    def __init__(self, base_dir: str | Path = "data/qa_v1/sessions") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _safe_session_id(self, session_id: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id.strip())
        if not safe:
            raise ValueError("session_id is required")
        return safe

    def _db_path(self, session_id: str) -> Path:
        safe = self._safe_session_id(session_id)
        session_dir = self.base_dir / safe
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir / "context.db"

    def _connect(self, session_id: str) -> sqlite3.Connection:
        path = self._db_path(session_id)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS session_meta (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                doc_scope_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS turns (
                turn_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                user_query TEXT NOT NULL,
                assistant_answer TEXT,
                summary TEXT NOT NULL,
                intent_tag TEXT NOT NULL,
                confidence REAL NOT NULL,
                trace_id TEXT NOT NULL,
                status TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                topic_tags_json TEXT NOT NULL,
                entities_json TEXT NOT NULL,
                referenced_docs_json TEXT NOT NULL,
                citations_json TEXT NOT NULL,
                stage1_json TEXT NOT NULL,
                stage2_json TEXT NOT NULL,
                routing_plan_json TEXT NOT NULL,
                agent_runs_json TEXT NOT NULL,
                clarification_thread_id TEXT,
                error TEXT
            );

            CREATE TABLE IF NOT EXISTS turn_tags (
                turn_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY (turn_id, tag)
            );

            CREATE TABLE IF NOT EXISTS turn_entities (
                turn_id TEXT NOT NULL,
                entity TEXT NOT NULL,
                PRIMARY KEY (turn_id, entity)
            );

            CREATE TABLE IF NOT EXISTS clarifications (
                thread_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                original_query TEXT NOT NULL,
                question TEXT NOT NULL,
                options_json TEXT NOT NULL,
                ambiguity_points_json TEXT NOT NULL,
                status TEXT NOT NULL,
                answer TEXT,
                resolved_query TEXT
            );

            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id TEXT PRIMARY KEY,
                turn_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_turns_created ON turns(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_turns_status ON turns(status);
            CREATE INDEX IF NOT EXISTS idx_turns_intent ON turns(intent_tag);
            CREATE INDEX IF NOT EXISTS idx_turn_tags_tag ON turn_tags(tag);
            CREATE INDEX IF NOT EXISTS idx_turn_entities_entity ON turn_entities(entity);
            """
        )

    def create_session(self, session_id: str, doc_scope: list[str] | None = None) -> None:
        now = utc_now_iso()
        doc_scope_json = json.dumps(doc_scope or [], ensure_ascii=True)
        with self._connect(session_id) as conn:
            self._ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO session_meta(session_id, created_at, updated_at, status, doc_scope_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    updated_at=excluded.updated_at,
                    doc_scope_json=excluded.doc_scope_json
                """,
                (self._safe_session_id(session_id), now, now, "active", doc_scope_json),
            )

    def append_turn(self, turn: DialogueTurn) -> None:
        with self._connect(turn.session_id) as conn:
            self._ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO turns(
                    turn_id, session_id, created_at, updated_at, user_query, assistant_answer,
                    summary, intent_tag, confidence, trace_id, status, schema_version,
                    tags_json, topic_tags_json, entities_json, referenced_docs_json,
                    citations_json, stage1_json, stage2_json, routing_plan_json,
                    agent_runs_json, clarification_thread_id, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._turn_sql_values(turn),
            )
            self._reindex_turn(conn, turn.turn_id, turn.tags, turn.entities)

    def update_turn(self, session_id: str, turn_id: str, patch: dict[str, Any]) -> DialogueTurn:
        current = self.get_turn(session_id, turn_id)
        if current is None:
            raise KeyError(f"turn not found: {turn_id}")

        data = current.to_dict()
        data.update(patch)
        data["updated_at"] = utc_now_iso()
        updated_turn = DialogueTurn(**data)

        with self._connect(session_id) as conn:
            self._ensure_schema(conn)
            conn.execute("DELETE FROM turns WHERE turn_id = ?", (turn_id,))
            conn.execute(
                """
                INSERT INTO turns(
                    turn_id, session_id, created_at, updated_at, user_query, assistant_answer,
                    summary, intent_tag, confidence, trace_id, status, schema_version,
                    tags_json, topic_tags_json, entities_json, referenced_docs_json,
                    citations_json, stage1_json, stage2_json, routing_plan_json,
                    agent_runs_json, clarification_thread_id, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._turn_sql_values(updated_turn),
            )
            self._reindex_turn(conn, turn_id, updated_turn.tags, updated_turn.entities)
        return updated_turn

    def get_turn(self, session_id: str, turn_id: str) -> DialogueTurn | None:
        with self._connect(session_id) as conn:
            self._ensure_schema(conn)
            row = conn.execute("SELECT * FROM turns WHERE turn_id = ?", (turn_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_turn(row)

    def list_turns(self, session_id: str, limit: int = 50, offset: int = 0) -> list[DialogueTurn]:
        with self._connect(session_id) as conn:
            self._ensure_schema(conn)
            rows = conn.execute(
                "SELECT * FROM turns ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._row_to_turn(row) for row in rows]

    def search_turns(
        self,
        session_id: str,
        query: str = "",
        tags: list[str] | None = None,
        intent_tag: str | None = None,
        limit: int = 20,
    ) -> list[DialogueTurn]:
        sql = "SELECT DISTINCT t.* FROM turns t"
        params: list[Any] = []
        where: list[str] = []

        if tags:
            sql += " JOIN turn_tags tt ON t.turn_id = tt.turn_id"
            placeholders = ",".join("?" for _ in tags)
            where.append(f"tt.tag IN ({placeholders})")
            params.extend(tags)

        if query:
            where.append("(t.user_query LIKE ? OR COALESCE(t.assistant_answer, '') LIKE ? OR t.summary LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like, like])

        if intent_tag:
            where.append("t.intent_tag = ?")
            params.append(intent_tag)

        if where:
            sql += " WHERE " + " AND ".join(where)

        sql += " ORDER BY t.created_at DESC LIMIT ?"
        params.append(limit)

        with self._connect(session_id) as conn:
            self._ensure_schema(conn)
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_turn(row) for row in rows]

    def create_clarification(self, thread: ClarificationThread) -> None:
        with self._connect(thread.session_id) as conn:
            self._ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO clarifications(
                    thread_id, session_id, turn_id, created_at, updated_at, original_query,
                    question, options_json, ambiguity_points_json, status, answer, resolved_query
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    thread.thread_id,
                    thread.session_id,
                    thread.turn_id,
                    thread.created_at,
                    thread.updated_at,
                    thread.original_query,
                    thread.question,
                    json.dumps(thread.options, ensure_ascii=True),
                    json.dumps(thread.ambiguity_points, ensure_ascii=True),
                    thread.status,
                    thread.answer,
                    thread.resolved_query,
                ),
            )

    def get_clarification(self, session_id: str, thread_id: str) -> ClarificationThread | None:
        with self._connect(session_id) as conn:
            self._ensure_schema(conn)
            row = conn.execute(
                "SELECT * FROM clarifications WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        if row is None:
            return None
        return ClarificationThread(
            thread_id=row["thread_id"],
            session_id=row["session_id"],
            turn_id=row["turn_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            original_query=row["original_query"],
            question=row["question"],
            options=json.loads(row["options_json"]),
            ambiguity_points=json.loads(row["ambiguity_points_json"]),
            status=row["status"],
            answer=row["answer"],
            resolved_query=row["resolved_query"],
        )

    def resolve_clarification(
        self,
        session_id: str,
        thread_id: str,
        answer: str,
        resolved_query: str,
    ) -> ClarificationThread:
        thread = self.get_clarification(session_id, thread_id)
        if thread is None:
            raise KeyError(f"clarification not found: {thread_id}")
        now = utc_now_iso()
        with self._connect(session_id) as conn:
            self._ensure_schema(conn)
            conn.execute(
                """
                UPDATE clarifications
                SET updated_at = ?, status = ?, answer = ?, resolved_query = ?
                WHERE thread_id = ?
                """,
                (now, "resolved", answer, resolved_query, thread_id),
            )
        return ClarificationThread(
            thread_id=thread.thread_id,
            session_id=thread.session_id,
            turn_id=thread.turn_id,
            created_at=thread.created_at,
            updated_at=now,
            original_query=thread.original_query,
            question=thread.question,
            options=thread.options,
            ambiguity_points=thread.ambiguity_points,
            status="resolved",
            answer=answer,
            resolved_query=resolved_query,
        )

    def save_artifact(
        self,
        session_id: str,
        turn_id: str,
        artifact_id: str,
        artifact_type: str,
        payload: dict[str, Any],
    ) -> None:
        with self._connect(session_id) as conn:
            self._ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO artifacts(artifact_id, turn_id, session_id, artifact_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    turn_id,
                    session_id,
                    artifact_type,
                    json.dumps(payload, ensure_ascii=True),
                    utc_now_iso(),
                ),
            )

    def _turn_sql_values(self, turn: DialogueTurn) -> tuple[Any, ...]:
        return (
            turn.turn_id,
            turn.session_id,
            turn.created_at,
            turn.updated_at,
            turn.user_query,
            turn.assistant_answer,
            turn.summary,
            turn.intent_tag,
            float(turn.confidence),
            turn.trace_id,
            turn.status,
            turn.schema_version,
            json.dumps(turn.tags, ensure_ascii=True),
            json.dumps(turn.topic_tags, ensure_ascii=True),
            json.dumps(turn.entities, ensure_ascii=True),
            json.dumps(turn.referenced_docs, ensure_ascii=True),
            json.dumps(turn.citations, ensure_ascii=True),
            json.dumps(turn.stage1_result, ensure_ascii=True),
            json.dumps(turn.stage2_result, ensure_ascii=True),
            json.dumps(turn.routing_plan, ensure_ascii=True),
            json.dumps(turn.agent_runs, ensure_ascii=True),
            turn.clarification_thread_id,
            turn.error,
        )

    def _reindex_turn(
        self,
        conn: sqlite3.Connection,
        turn_id: str,
        tags: list[str],
        entities: list[dict[str, Any]],
    ) -> None:
        conn.execute("DELETE FROM turn_tags WHERE turn_id = ?", (turn_id,))
        conn.execute("DELETE FROM turn_entities WHERE turn_id = ?", (turn_id,))
        for tag in {tag.strip() for tag in tags if tag and tag.strip()}:
            conn.execute("INSERT OR IGNORE INTO turn_tags(turn_id, tag) VALUES (?, ?)", (turn_id, tag))
        for entity in entities:
            value = str(entity.get("value", "")).strip()
            if value:
                conn.execute(
                    "INSERT OR IGNORE INTO turn_entities(turn_id, entity) VALUES (?, ?)",
                    (turn_id, value),
                )

    def _row_to_turn(self, row: sqlite3.Row) -> DialogueTurn:
        return DialogueTurn(
            turn_id=row["turn_id"],
            session_id=row["session_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            user_query=row["user_query"],
            assistant_answer=row["assistant_answer"],
            summary=row["summary"],
            tags=json.loads(row["tags_json"]),
            topic_tags=json.loads(row["topic_tags_json"]),
            intent_tag=row["intent_tag"],
            entities=json.loads(row["entities_json"]),
            referenced_docs=json.loads(row["referenced_docs_json"]),
            citations=json.loads(row["citations_json"]),
            stage1_result=json.loads(row["stage1_json"]),
            stage2_result=json.loads(row["stage2_json"]),
            routing_plan=json.loads(row["routing_plan_json"]),
            agent_runs=json.loads(row["agent_runs_json"]),
            confidence=float(row["confidence"]),
            trace_id=row["trace_id"],
            status=row["status"],
            clarification_thread_id=row["clarification_thread_id"],
            error=row["error"],
            schema_version=row["schema_version"],
        )
