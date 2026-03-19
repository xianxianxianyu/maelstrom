from __future__ import annotations

import aiosqlite

TABLES_DDL = [
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL DEFAULT 'Untitled Session',
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS artifacts (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        type TEXT NOT NULL,
        data_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        citations_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gap_runs (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        topic TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        result_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        completed_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_papers (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES gap_runs(id) ON DELETE CASCADE,
        paper_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS synthesis_runs (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        topic TEXT NOT NULL,
        source_gap_id TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        result_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        completed_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence_memory (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        source_type TEXT NOT NULL,
        source_id TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        content TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS planning_runs (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        topic TEXT NOT NULL,
        source_synthesis_id TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        result_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        completed_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS experiment_runs (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        topic TEXT NOT NULL,
        source_plan_id TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        result_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        completed_at TEXT
    )
    """,
    # ── P2 tables ────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS trace_events (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        engine TEXT NOT NULL DEFAULT '',
        event_type TEXT NOT NULL,
        node_name TEXT DEFAULT NULL,
        timestamp TEXT NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_trace_events_run ON trace_events(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_trace_events_session ON trace_events(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_trace_events_timestamp ON trace_events(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_trace_events_engine_type ON trace_events(engine, event_type)",
    """
    CREATE TABLE IF NOT EXISTS evidence_edges (
        id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL,
        source_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        target_type TEXT NOT NULL,
        relation TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_evidence_edges_source ON evidence_edges(source_id)",
    "CREATE INDEX IF NOT EXISTS idx_evidence_edges_target ON evidence_edges(target_id)",
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS approvals (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        approval_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        payload_json TEXT NOT NULL DEFAULT '{}',
        requested_at TEXT NOT NULL,
        resolved_at TEXT,
        resolved_by TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS policies (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL UNIQUE,
        config_json TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL
    )
    """,
    # ── P3 eval tables ────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS eval_runs (
        id TEXT PRIMARY KEY,
        mode TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        engine_filter TEXT DEFAULT NULL,
        target_run_id TEXT DEFAULT NULL,
        target_session_id TEXT DEFAULT NULL,
        summary_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        completed_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_eval_runs_status ON eval_runs(status)",
    """
    CREATE TABLE IF NOT EXISTS eval_case_results (
        id TEXT PRIMARY KEY,
        eval_run_id TEXT NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
        case_id TEXT NOT NULL,
        engine TEXT NOT NULL,
        passed INTEGER NOT NULL DEFAULT 0,
        schema_valid INTEGER NOT NULL DEFAULT 1,
        quality_checks_json TEXT NOT NULL DEFAULT '{}',
        output_json TEXT NOT NULL DEFAULT '{}',
        error TEXT DEFAULT NULL,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_eval_case_results_run ON eval_case_results(eval_run_id)",
]

# FTS and triggers must be created after the physical table.
_FTS_DDL = [
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS evidence_memory_fts USING fts5(
        title, content,
        content='evidence_memory',
        content_rowid='rowid',
        tokenize='unicode61'
    )
    """,
]

_TRIGGER_DDL = [
    """
    CREATE TRIGGER IF NOT EXISTS evidence_memory_ai AFTER INSERT ON evidence_memory BEGIN
        INSERT INTO evidence_memory_fts(rowid, title, content)
        VALUES (new.rowid, new.title, new.content);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS evidence_memory_ad AFTER DELETE ON evidence_memory BEGIN
        INSERT INTO evidence_memory_fts(evidence_memory_fts, rowid, title, content)
        VALUES ('delete', old.rowid, old.title, old.content);
    END
    """,
]

# Incremental ALTER TABLE migrations (idempotent)
_ALTER_DDL = [
    ("chat_messages", "intent", "ALTER TABLE chat_messages ADD COLUMN intent TEXT DEFAULT NULL"),
    ("sessions", "current_phase", "ALTER TABLE sessions ADD COLUMN current_phase TEXT DEFAULT 'ideation'"),
    ("sessions", "phase_updated_at", "ALTER TABLE sessions ADD COLUMN phase_updated_at TEXT DEFAULT NULL"),
    ("sessions", "user_id", "ALTER TABLE sessions ADD COLUMN user_id TEXT DEFAULT NULL"),
    # Node-level checkpoint for run recovery
    ("gap_runs", "current_step", "ALTER TABLE gap_runs ADD COLUMN current_step TEXT DEFAULT NULL"),
    ("gap_runs", "progress_json", "ALTER TABLE gap_runs ADD COLUMN progress_json TEXT NOT NULL DEFAULT '{}'"),
    ("synthesis_runs", "current_step", "ALTER TABLE synthesis_runs ADD COLUMN current_step TEXT DEFAULT NULL"),
    ("synthesis_runs", "progress_json", "ALTER TABLE synthesis_runs ADD COLUMN progress_json TEXT NOT NULL DEFAULT '{}'"),
    ("planning_runs", "current_step", "ALTER TABLE planning_runs ADD COLUMN current_step TEXT DEFAULT NULL"),
    ("planning_runs", "progress_json", "ALTER TABLE planning_runs ADD COLUMN progress_json TEXT NOT NULL DEFAULT '{}'"),
    ("experiment_runs", "current_step", "ALTER TABLE experiment_runs ADD COLUMN current_step TEXT DEFAULT NULL"),
    ("experiment_runs", "progress_json", "ALTER TABLE experiment_runs ADD COLUMN progress_json TEXT NOT NULL DEFAULT '{}'"),
]


async def run_migrations(db: aiosqlite.Connection) -> None:
    for ddl in TABLES_DDL:
        await db.execute(ddl)
    for ddl in _FTS_DDL:
        await db.execute(ddl)
    for ddl in _TRIGGER_DDL:
        await db.execute(ddl)
    # Idempotent ALTER TABLE migrations
    for table, column, alter_sql in _ALTER_DDL:
        try:
            await db.execute(alter_sql)
        except Exception:
            pass  # Column already exists
    await db.commit()
