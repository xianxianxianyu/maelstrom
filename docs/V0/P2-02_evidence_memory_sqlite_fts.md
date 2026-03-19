# P2-02: EvidenceMemory — SQLite FTS 简化版

## 依赖
- P0-01（Pydantic Schema — PaperRecord, GapItem）
- P0-00（SQLite + aiosqlite 基础设施）
- P1-07（normalize_dedup — PaperRecord 已入库）

## 目的
实现基于 SQLite FTS5 的 EvidenceMemory，为意图分类器和未来的 Synthesis Engine 提供会话级文档检索能力。不引入向量数据库，用 SQLite 全文搜索做简化版。

## 设计决策
- **不用向量搜索**：V0 阶段用 SQLite FTS5 全文匹配，足够支撑意图分类上下文和简单的证据检索
- **迁移路径**：接口设计为 `EvidenceMemory` ABC，未来 V1 可替换为向量搜索实现

## 执行方法

### 1. DB Migration — 新增 FTS 表

在 `src/maelstrom/db/migrations.py` 的 `TABLES_DDL` 中追加：

```sql
-- 证据记忆表（物理表）
CREATE TABLE IF NOT EXISTS evidence_memory (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,          -- 'paper' | 'gap' | 'chat' | 'claim'
    source_id TEXT NOT NULL,            -- 原始记录 ID
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,              -- 可搜索的文本内容
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

-- FTS5 虚拟表
CREATE VIRTUAL TABLE IF NOT EXISTS evidence_memory_fts USING fts5(
    title, content,
    content='evidence_memory',
    content_rowid='rowid',
    tokenize='unicode61'
);

-- 触发器：同步 FTS 索引
CREATE TRIGGER IF NOT EXISTS evidence_memory_ai AFTER INSERT ON evidence_memory BEGIN
    INSERT INTO evidence_memory_fts(rowid, title, content)
    VALUES (new.rowid, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS evidence_memory_ad AFTER DELETE ON evidence_memory BEGIN
    INSERT INTO evidence_memory_fts(evidence_memory_fts, rowid, title, content)
    VALUES ('delete', old.rowid, old.title, old.content);
END;
```

### 2. EvidenceMemory 抽象接口 — `src/maelstrom/services/evidence_memory.py`

```python
class EvidenceMemoryBase(ABC):
    @abstractmethod
    async def ingest_paper(self, session_id: str, paper: PaperRecord) -> str: ...
    @abstractmethod
    async def ingest_gap(self, session_id: str, gap: GapItem) -> str: ...
    @abstractmethod
    async def ingest_text(self, session_id: str, source_type: str, source_id: str, title: str, content: str) -> str: ...
    @abstractmethod
    async def search(self, session_id: str, query: str, limit: int = 10) -> list[EvidenceHit]: ...
    @abstractmethod
    async def get_session_summary(self, session_id: str) -> SessionMemorySummary: ...

class EvidenceHit(BaseModel):
    evidence_id: str
    source_type: str
    source_id: str
    title: str
    snippet: str          # FTS highlight 片段
    rank: float           # BM25 分数

class SessionMemorySummary(BaseModel):
    session_id: str
    paper_count: int
    gap_count: int
    chat_count: int
    total_entries: int
```

### 3. SQLite FTS 实现 — `src/maelstrom/services/sqlite_evidence_memory.py`

```python
class SqliteEvidenceMemory(EvidenceMemoryBase):
    async def ingest_paper(self, session_id, paper):
        content = f"{paper.abstract or ''}\n{' '.join(a.name for a in paper.authors)}"
        return await self.ingest_text(session_id, "paper", paper.paper_id, paper.title, content)

    async def ingest_gap(self, session_id, gap):
        content = f"{gap.summary}\nType: {', '.join(gap.gap_type)}"
        return await self.ingest_text(session_id, "gap", gap.gap_id, gap.title, content)

    async def search(self, session_id, query, limit=10):
        # FTS5 MATCH + BM25 ranking + session_id 过滤
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
        ...
```

### 4. Gap Engine 集成钩子

在 Gap Engine 完成后自动将结果写入 EvidenceMemory：
- `ranking_packaging` 节点完成后，调用 `ingest_paper` 批量写入去重后的论文
- 调用 `ingest_gap` 批量写入 ranked_gaps
- 这通过在 `gap_service.py` 的 `_run_gap_engine` 末尾添加 ingest 调用实现

## 验收条件
- `evidence_memory` 表和 FTS5 虚拟表正确创建
- 触发器正确同步 FTS 索引
- `ingest_paper` 将 PaperRecord 写入 evidence_memory 并可被 FTS 搜索
- `ingest_gap` 将 GapItem 写入 evidence_memory 并可被 FTS 搜索
- `search` 返回按 BM25 排序的结果，包含 highlight snippet
- `search` 正确按 session_id 隔离
- `get_session_summary` 返回正确的计数
- Gap Engine 完成后自动 ingest 论文和 gap

## Unit Test
- `test_evidence_memory_table_created`: 验证 migration 创建 evidence_memory + FTS 表
- `test_ingest_paper`: 写入 PaperRecord → 可通过标题搜索到
- `test_ingest_gap`: 写入 GapItem → 可通过 summary 关键词搜索到
- `test_ingest_text`: 写入自由文本 → 可搜索
- `test_search_bm25_ranking`: 多条记录 → 搜索结果按相关性排序
- `test_search_session_isolation`: session_A 的记录不出现在 session_B 的搜索中
- `test_search_highlight_snippet`: 搜索结果包含 `<b>` 高亮片段
- `test_search_no_results`: 无匹配时返回空列表
- `test_get_session_summary`: 写入 3 paper + 2 gap → summary 计数正确
- `test_gap_engine_auto_ingest`: mock gap engine 完成 → evidence_memory 中有对应记录
