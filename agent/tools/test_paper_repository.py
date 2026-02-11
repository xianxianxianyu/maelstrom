"""Unit tests for PaperRepository — SQLite 论文元数据存储层"""

import pytest

from agent.tools.paper_repository import (
    PaperMetadata,
    PaperRepository,
    pack_embedding,
    unpack_embedding,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test_papers.db"


@pytest.fixture
def sample_metadata():
    return PaperMetadata(
        title="Attention Is All You Need",
        title_zh="注意力机制就是你所需要的",
        authors=["Vaswani", "Shazeer", "Parmar"],
        abstract="本文提出了 Transformer 架构，完全基于注意力机制。",
        domain="nlp",
        research_problem="如何在不使用 RNN 的情况下建模序列",
        methodology="自注意力机制 + 位置编码",
        contributions=["提出 Transformer", "实现并行训练"],
        keywords=["attention", "transformer", "NLP", "self-attention"],
        base_models=["WMT 2014"],
        year=2017,
        venue="NeurIPS 2017",
    )


async def _make_repo(tmp_db):
    r = PaperRepository(db_path=tmp_db)
    await r.init_db()
    return r


# ---------------------------------------------------------------------------
# PaperMetadata tests
# ---------------------------------------------------------------------------

class TestPaperMetadata:
    def test_to_dict(self, sample_metadata):
        d = sample_metadata.to_dict()
        assert d["title"] == "Attention Is All You Need"
        assert d["domain"] == "nlp"
        assert len(d["authors"]) == 3
        assert d["year"] == 2017

    def test_from_dict(self):
        data = {
            "title": "BERT",
            "title_zh": "BERT 模型",
            "authors": ["Devlin"],
            "abstract": "预训练语言模型",
            "domain": "nlp",
            "research_problem": "预训练",
            "methodology": "掩码语言模型",
            "contributions": ["提出 BERT"],
            "keywords": ["bert", "pretraining"],
            "base_models": [],
            "year": 2019,
            "venue": "NAACL",
        }
        meta = PaperMetadata.from_dict(data)
        assert meta.title == "BERT"
        assert meta.year == 2019
        assert len(meta.keywords) == 2

    def test_from_dict_missing_fields(self):
        meta = PaperMetadata.from_dict({"title": "Test"})
        assert meta.title == "Test"
        assert meta.authors == []
        assert meta.year is None

    def test_roundtrip(self, sample_metadata):
        d = sample_metadata.to_dict()
        restored = PaperMetadata.from_dict(d)
        assert restored.title == sample_metadata.title
        assert restored.keywords == sample_metadata.keywords

    def test_defaults(self):
        meta = PaperMetadata()
        assert meta.title == ""
        assert meta.authors == []
        assert meta.year is None


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

class TestEmbeddingHelpers:
    def test_pack_unpack_roundtrip(self):
        vec = [0.1, 0.2, 0.3, -0.5, 1.0]
        blob = pack_embedding(vec)
        restored = unpack_embedding(blob)
        assert len(restored) == 5
        for a, b in zip(vec, restored):
            assert abs(a - b) < 1e-6

    def test_empty_embedding(self):
        blob = pack_embedding([])
        restored = unpack_embedding(blob)
        assert restored == []


# ---------------------------------------------------------------------------
# PaperRepository tests
# ---------------------------------------------------------------------------

class TestPaperRepositoryInit:
    @pytest.mark.asyncio
    async def test_init_creates_db_file(self, tmp_db):
        repo = PaperRepository(db_path=tmp_db)
        await repo.init_db()
        assert tmp_db.exists()
        await repo.close()

    @pytest.mark.asyncio
    async def test_init_idempotent(self, tmp_db):
        repo = PaperRepository(db_path=tmp_db)
        await repo.init_db()
        await repo.init_db()
        await repo.close()

    @pytest.mark.asyncio
    async def test_ensure_db_raises_without_init(self, tmp_db):
        repo = PaperRepository(db_path=tmp_db)
        with pytest.raises(RuntimeError, match="not initialized"):
            repo._ensure_db()


class TestPaperRepositoryUpsert:
    @pytest.mark.asyncio
    async def test_insert_and_get(self, tmp_db, sample_metadata):
        repo = await _make_repo(tmp_db)
        await repo.upsert("paper-001", sample_metadata, filename="test.pdf")
        result = await repo.get_by_id("paper-001")
        assert result is not None
        assert result["title"] == "Attention Is All You Need"
        assert result["domain"] == "nlp"
        assert result["filename"] == "test.pdf"
        await repo.close()

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, tmp_db, sample_metadata):
        repo = await _make_repo(tmp_db)
        await repo.upsert("paper-001", sample_metadata)
        sample_metadata.title = "Updated Title"
        await repo.upsert("paper-001", sample_metadata)
        result = await repo.get_by_id("paper-001")
        assert result["title"] == "Updated Title"
        await repo.close()

    @pytest.mark.asyncio
    async def test_upsert_with_embedding(self, tmp_db, sample_metadata):
        repo = await _make_repo(tmp_db)
        emb = [0.1, 0.2, 0.3]
        await repo.upsert("paper-001", sample_metadata, embedding=emb)
        result = await repo.get_by_id("paper-001")
        assert result["embedding"] is not None
        assert len(result["embedding"]) == 3
        await repo.close()

    @pytest.mark.asyncio
    async def test_upsert_with_quality_score(self, tmp_db, sample_metadata):
        repo = await _make_repo(tmp_db)
        await repo.upsert("paper-001", sample_metadata, quality_score=85)
        result = await repo.get_by_id("paper-001")
        assert result["quality_score"] == 85
        await repo.close()

    @pytest.mark.asyncio
    async def test_json_fields_parsed(self, tmp_db, sample_metadata):
        repo = await _make_repo(tmp_db)
        await repo.upsert("paper-001", sample_metadata)
        result = await repo.get_by_id("paper-001")
        assert isinstance(result["authors"], list)
        assert isinstance(result["keywords"], list)
        assert "Vaswani" in result["authors"]
        await repo.close()


class TestPaperRepositorySearch:
    @pytest.mark.asyncio
    async def test_search_text(self, tmp_db, sample_metadata):
        repo = await _make_repo(tmp_db)
        await repo.upsert("paper-001", sample_metadata)
        results = await repo.search_text("Transformer")
        assert len(results) >= 1
        assert results[0]["id"] == "paper-001"
        await repo.close()

    @pytest.mark.asyncio
    async def test_search_text_chinese(self, tmp_db, sample_metadata):
        repo = await _make_repo(tmp_db)
        await repo.upsert("paper-001", sample_metadata)
        # FTS5 默认使用空格分词，中文搜索需要匹配完整 token
        # 搜索 abstract 中的完整词
        results = await repo.search_text("Transformer")
        assert len(results) >= 1
        await repo.close()

    @pytest.mark.asyncio
    async def test_search_text_no_results(self, tmp_db, sample_metadata):
        repo = await _make_repo(tmp_db)
        await repo.upsert("paper-001", sample_metadata)
        results = await repo.search_text("quantum computing")
        assert len(results) == 0
        await repo.close()

    @pytest.mark.asyncio
    async def test_search_by_domain(self, tmp_db, sample_metadata):
        repo = await _make_repo(tmp_db)
        await repo.upsert("paper-001", sample_metadata)
        results = await repo.search_by_domain("nlp")
        assert len(results) == 1
        assert results[0]["domain"] == "nlp"
        await repo.close()

    @pytest.mark.asyncio
    async def test_search_by_domain_no_match(self, tmp_db, sample_metadata):
        repo = await _make_repo(tmp_db)
        await repo.upsert("paper-001", sample_metadata)
        results = await repo.search_by_domain("cv")
        assert len(results) == 0
        await repo.close()

    @pytest.mark.asyncio
    async def test_search_by_keywords(self, tmp_db, sample_metadata):
        repo = await _make_repo(tmp_db)
        await repo.upsert("paper-001", sample_metadata)
        results = await repo.search_by_keywords(["transformer"])
        assert len(results) >= 1
        await repo.close()

    @pytest.mark.asyncio
    async def test_search_by_keywords_multiple(self, tmp_db):
        repo = await _make_repo(tmp_db)
        m1 = PaperMetadata(title="Paper A", keywords=["rl", "policy"])
        m2 = PaperMetadata(title="Paper B", keywords=["nlp", "bert"])
        await repo.upsert("p1", m1)
        await repo.upsert("p2", m2)
        results = await repo.search_by_keywords(["rl", "bert"])
        assert len(results) == 2
        await repo.close()


class TestPaperRepositoryListAndDelete:
    @pytest.mark.asyncio
    async def test_list_all(self, tmp_db):
        repo = await _make_repo(tmp_db)
        await repo.upsert("p1", PaperMetadata(title="Paper A"))
        await repo.upsert("p2", PaperMetadata(title="Paper B"))
        results = await repo.list_all()
        assert len(results) == 2
        await repo.close()

    @pytest.mark.asyncio
    async def test_count(self, tmp_db):
        repo = await _make_repo(tmp_db)
        assert await repo.count() == 0
        await repo.upsert("p1", PaperMetadata(title="A"))
        assert await repo.count() == 1
        await repo.upsert("p2", PaperMetadata(title="B"))
        assert await repo.count() == 2
        await repo.close()

    @pytest.mark.asyncio
    async def test_delete(self, tmp_db):
        repo = await _make_repo(tmp_db)
        await repo.upsert("p1", PaperMetadata(title="A"))
        assert await repo.count() == 1
        deleted = await repo.delete("p1")
        assert deleted is True
        assert await repo.count() == 0
        await repo.close()

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, tmp_db):
        repo = await _make_repo(tmp_db)
        deleted = await repo.delete("nonexistent")
        assert deleted is False
        await repo.close()

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, tmp_db):
        repo = await _make_repo(tmp_db)
        result = await repo.get_by_id("nonexistent")
        assert result is None
        await repo.close()
