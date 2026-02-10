"""Unit tests for DocSearchTool and VectorIndex.

Validates:
- VectorIndex splits documents into chunks (~500 chars) (Requirements 4.1)
- VectorIndex indexes documents and retrieves by cosine similarity (Requirements 4.1, 4.2)
- VectorIndex isolates search results by doc_id (Requirements 4.2, 4.5)
- VectorIndex clear removes chunks correctly (Requirements 4.1)
- DocSearchTool implements BaseTool interface correctly (Requirements 5.2)
- action="search" returns matching chunks via VectorIndex (Requirements 5.3)
- action="index" indexes a document and returns chunk count (Requirements 5.3)
- action="clear" clears the index (Requirements 5.3)
- Unknown action returns structured error with recoverable=False (Requirements 5.4)
- Missing/invalid arguments return structured errors (Requirements 5.4)
"""

from __future__ import annotations

import numpy as np
import pytest

from agent.tools.base import BaseTool, ToolResult
from agent.tools.doc_search_tool import DocSearchTool, VectorIndex


class TestVectorIndexChunking:

    def test_split_by_double_newline(self):
        vi = VectorIndex()
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunks = vi._split_into_chunks(text)
        assert len(chunks) >= 1
        assert "Paragraph one." in chunks[0]

    def test_empty_text_returns_empty(self):
        vi = VectorIndex()
        assert vi._split_into_chunks("") == []
        assert vi._split_into_chunks("   ") == []
        assert vi._split_into_chunks("\n\n") == []

    def test_single_paragraph(self):
        vi = VectorIndex()
        text = "This is a single paragraph."
        chunks = vi._split_into_chunks(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_small_paragraphs_merged(self):
        vi = VectorIndex()
        paragraphs = [f"Short paragraph {i}." for i in range(20)]
        text = "\n\n".join(paragraphs)
        chunks = vi._split_into_chunks(text)
        assert len(chunks) < len(paragraphs)

    def test_large_paragraphs_not_merged(self):
        vi = VectorIndex()
        para1 = "A" * 600
        para2 = "B" * 600
        text = f"{para1}\n\n{para2}"
        chunks = vi._split_into_chunks(text)
        assert len(chunks) == 2
        assert chunks[0] == para1
        assert chunks[1] == para2


# ---------------------------------------------------------------------------
# VectorIndex: embedding tests
# ---------------------------------------------------------------------------


class TestVectorIndexEmbedding:
    """Tests for VectorIndex._get_embedding."""

    @pytest.mark.asyncio
    async def test_embedding_is_deterministic(self):
        vi = VectorIndex()
        emb1 = await vi._get_embedding("hello world")
        emb2 = await vi._get_embedding("hello world")
        np.testing.assert_array_equal(emb1, emb2)

    @pytest.mark.asyncio
    async def test_embedding_dimension(self):
        vi = VectorIndex()
        emb = await vi._get_embedding("test text")
        assert emb.shape == (128,)

    @pytest.mark.asyncio
    async def test_embedding_is_normalized(self):
        vi = VectorIndex()
        emb = await vi._get_embedding("some text")
        norm = np.linalg.norm(emb)
        assert abs(norm - 1.0) < 1e-6

    @pytest.mark.asyncio
    async def test_different_texts_different_embeddings(self):
        vi = VectorIndex()
        emb1 = await vi._get_embedding("hello")
        emb2 = await vi._get_embedding("world")
        assert not np.array_equal(emb1, emb2)


# ---------------------------------------------------------------------------
# VectorIndex: cosine similarity tests
# ---------------------------------------------------------------------------


class TestVectorIndexCosineSim:
    """Tests for VectorIndex._cosine_sim."""

    def test_identical_vectors(self):
        a = np.array([1.0, 0.0, 0.0])
        sim = VectorIndex._cosine_sim(a, a)
        assert abs(sim - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        sim = VectorIndex._cosine_sim(a, b)
        assert abs(sim) < 1e-6

    def test_opposite_vectors(self):
        a = np.array([1.0, 0.0])
        b = np.array([-1.0, 0.0])
        sim = VectorIndex._cosine_sim(a, b)
        assert abs(sim + 1.0) < 1e-6


# ---------------------------------------------------------------------------
# VectorIndex: index and search tests
# ---------------------------------------------------------------------------


class TestVectorIndexIndexAndSearch:
    """Tests for VectorIndex.index_document and search."""

    @pytest.mark.asyncio
    async def test_index_document_returns_chunk_count(self):
        vi = VectorIndex()
        count = await vi.index_document("doc1", "Para one.\n\nPara two.", "test.pdf")
        assert count >= 1
        assert vi.chunk_count == count

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        vi = VectorIndex()
        await vi.index_document(
            "doc1",
            "Machine learning is great.\n\nDeep learning is powerful.",
            "ml.pdf",
        )
        results = await vi.search("machine learning")
        assert len(results) > 0
        assert "text" in results[0]
        assert "source" in results[0]
        assert "score" in results[0]

    @pytest.mark.asyncio
    async def test_search_empty_index(self):
        vi = VectorIndex()
        results = await vi.search("anything")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_respects_top_k(self):
        vi = VectorIndex()
        paragraphs = [f"Topic {i}: " + "x" * 600 for i in range(10)]
        text = "\n\n".join(paragraphs)
        await vi.index_document("doc1", text, "test.pdf")
        results = await vi.search("topic", top_k=3)
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_search_results_sorted_by_score(self):
        vi = VectorIndex()
        await vi.index_document(
            "doc1",
            "Alpha content.\n\n" + "B" * 600 + "\n\n" + "C" * 600,
            "test.pdf",
        )
        results = await vi.search("Alpha content")
        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i]["score"] >= results[i + 1]["score"]

    @pytest.mark.asyncio
    async def test_search_source_matches_doc_name(self):
        vi = VectorIndex()
        await vi.index_document("doc1", "Some content here.", "my_paper.pdf")
        results = await vi.search("content")
        assert len(results) > 0
        assert results[0]["source"] == "my_paper.pdf"


# ---------------------------------------------------------------------------
# VectorIndex: doc_id isolation tests
# ---------------------------------------------------------------------------


class TestVectorIndexDocIdIsolation:
    """Tests for doc_id-based search isolation."""

    @pytest.mark.asyncio
    async def test_search_with_doc_id_filters_results(self):
        vi = VectorIndex()
        await vi.index_document("doc1", "Machine learning paper content.", "ml.pdf")
        await vi.index_document("doc2", "Computer vision paper content.", "cv.pdf")
        results = await vi.search("paper content", doc_id="doc1")
        for r in results:
            assert r["source"] == "ml.pdf"

    @pytest.mark.asyncio
    async def test_search_without_doc_id_returns_all(self):
        vi = VectorIndex()
        await vi.index_document("doc1", "Machine learning paper.", "ml.pdf")
        await vi.index_document("doc2", "Computer vision paper.", "cv.pdf")
        results = await vi.search("paper", top_k=10)
        sources = {r["source"] for r in results}
        assert len(sources) == 2

    @pytest.mark.asyncio
    async def test_search_nonexistent_doc_id_returns_empty(self):
        vi = VectorIndex()
        await vi.index_document("doc1", "Some content.", "test.pdf")
        results = await vi.search("content", doc_id="nonexistent")
        assert results == []


# ---------------------------------------------------------------------------
# VectorIndex: clear tests
# ---------------------------------------------------------------------------


class TestVectorIndexClear:
    """Tests for VectorIndex.clear."""

    @pytest.mark.asyncio
    async def test_clear_all(self):
        vi = VectorIndex()
        await vi.index_document("doc1", "Content one.", "a.pdf")
        await vi.index_document("doc2", "Content two.", "b.pdf")
        assert vi.chunk_count > 0
        removed = vi.clear()
        assert removed > 0
        assert vi.chunk_count == 0

    @pytest.mark.asyncio
    async def test_clear_specific_doc_id(self):
        vi = VectorIndex()
        await vi.index_document("doc1", "Content one.", "a.pdf")
        await vi.index_document("doc2", "Content two.", "b.pdf")
        total = vi.chunk_count
        removed = vi.clear(doc_id="doc1")
        assert removed > 0
        assert vi.chunk_count < total
        results = await vi.search("Content", top_k=100)
        for r in results:
            assert r["source"] == "b.pdf"

    @pytest.mark.asyncio
    async def test_clear_nonexistent_doc_id(self):
        vi = VectorIndex()
        await vi.index_document("doc1", "Content.", "a.pdf")
        original = vi.chunk_count
        removed = vi.clear(doc_id="nonexistent")
        assert removed == 0
        assert vi.chunk_count == original


# ---------------------------------------------------------------------------
# DocSearchTool: interface tests
# ---------------------------------------------------------------------------


class TestDocSearchToolInterface:
    """Tests that DocSearchTool correctly implements the BaseTool ABC."""

    def test_is_subclass_of_base_tool(self):
        assert issubclass(DocSearchTool, BaseTool)

    def test_can_instantiate(self):
        tool = DocSearchTool()
        assert isinstance(tool, BaseTool)

    def test_can_instantiate_with_custom_index(self):
        index = VectorIndex()
        tool = DocSearchTool(vector_index=index)
        assert isinstance(tool, BaseTool)

    def test_name_property(self):
        tool = DocSearchTool()
        assert tool.name == "doc_search"

    def test_description_property(self):
        tool = DocSearchTool()
        assert isinstance(tool.description, str)
        assert len(tool.description) > 0


# ---------------------------------------------------------------------------
# DocSearchTool: action validation tests
# ---------------------------------------------------------------------------


class TestDocSearchToolActionValidation:
    """Tests for action parameter validation."""

    @pytest.mark.asyncio
    async def test_missing_action(self):
        tool = DocSearchTool()
        result = await tool.execute()
        assert result.success is False
        assert "action" in result.error
        assert result.recoverable is False

    @pytest.mark.asyncio
    async def test_invalid_action_type(self):
        tool = DocSearchTool()
        result = await tool.execute(action=123)
        assert result.success is False
        assert "str" in result.error
        assert result.recoverable is False

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        tool = DocSearchTool()
        result = await tool.execute(action="delete")
        assert result.success is False
        assert "Unknown action: delete" in result.error
        assert result.recoverable is False


# ---------------------------------------------------------------------------
# DocSearchTool: search action tests
# ---------------------------------------------------------------------------


class TestDocSearchToolSearch:
    """Tests for action='search'."""

    @pytest.mark.asyncio
    async def test_search_returns_chunks(self):
        index = VectorIndex()
        await index.index_document("doc1", "Machine learning is great.", "ml.pdf")
        tool = DocSearchTool(vector_index=index)
        result = await tool.execute(action="search", query="machine learning")
        assert result.success is True
        assert "chunks" in result.data
        assert len(result.data["chunks"]) > 0

    @pytest.mark.asyncio
    async def test_search_empty_index(self):
        tool = DocSearchTool()
        result = await tool.execute(action="search", query="anything")
        assert result.success is True
        assert result.data["chunks"] == []

    @pytest.mark.asyncio
    async def test_search_with_doc_id(self):
        index = VectorIndex()
        await index.index_document("doc1", "ML content.", "ml.pdf")
        await index.index_document("doc2", "CV content.", "cv.pdf")
        tool = DocSearchTool(vector_index=index)
        result = await tool.execute(action="search", query="content", doc_id="doc1")
        assert result.success is True
        for chunk in result.data["chunks"]:
            assert chunk["source"] == "ml.pdf"

    @pytest.mark.asyncio
    async def test_search_with_top_k(self):
        index = VectorIndex()
        paragraphs = [f"Topic {i}: " + "x" * 600 for i in range(10)]
        await index.index_document("doc1", "\n\n".join(paragraphs), "test.pdf")
        tool = DocSearchTool(vector_index=index)
        result = await tool.execute(action="search", query="topic", top_k=2)
        assert result.success is True
        assert len(result.data["chunks"]) <= 2

    @pytest.mark.asyncio
    async def test_search_missing_query(self):
        tool = DocSearchTool()
        result = await tool.execute(action="search")
        assert result.success is False
        assert "query" in result.error
        assert result.recoverable is False

    @pytest.mark.asyncio
    async def test_search_invalid_query_type(self):
        tool = DocSearchTool()
        result = await tool.execute(action="search", query=42)
        assert result.success is False
        assert "str" in result.error
        assert result.recoverable is False

    @pytest.mark.asyncio
    async def test_search_invalid_top_k_type(self):
        tool = DocSearchTool()
        result = await tool.execute(action="search", query="test", top_k="five")
        assert result.success is False
        assert "int" in result.error
        assert result.recoverable is False


# ---------------------------------------------------------------------------
# DocSearchTool: index action tests
# ---------------------------------------------------------------------------


class TestDocSearchToolIndex:
    """Tests for action='index'."""

    @pytest.mark.asyncio
    async def test_index_document(self):
        tool = DocSearchTool()
        result = await tool.execute(
            action="index",
            doc_id="doc1",
            markdown="Paragraph one.\n\nParagraph two.",
            doc_name="test.pdf",
        )
        assert result.success is True
        assert result.data["indexed_chunks"] >= 1
        assert result.data["doc_id"] == "doc1"

    @pytest.mark.asyncio
    async def test_index_empty_markdown(self):
        tool = DocSearchTool()
        result = await tool.execute(
            action="index",
            doc_id="doc1",
            markdown="",
            doc_name="empty.pdf",
        )
        assert result.success is True
        assert result.data["indexed_chunks"] == 0

    @pytest.mark.asyncio
    async def test_index_missing_doc_id(self):
        tool = DocSearchTool()
        result = await tool.execute(
            action="index", markdown="content", doc_name="test.pdf"
        )
        assert result.success is False
        assert "doc_id" in result.error
        assert result.recoverable is False

    @pytest.mark.asyncio
    async def test_index_missing_markdown(self):
        tool = DocSearchTool()
        result = await tool.execute(
            action="index", doc_id="doc1", doc_name="test.pdf"
        )
        assert result.success is False
        assert "markdown" in result.error
        assert result.recoverable is False

    @pytest.mark.asyncio
    async def test_index_missing_doc_name(self):
        tool = DocSearchTool()
        result = await tool.execute(
            action="index", doc_id="doc1", markdown="content"
        )
        assert result.success is False
        assert "doc_name" in result.error
        assert result.recoverable is False

    @pytest.mark.asyncio
    async def test_index_missing_multiple_args(self):
        tool = DocSearchTool()
        result = await tool.execute(action="index")
        assert result.success is False
        assert "doc_id" in result.error
        assert "markdown" in result.error
        assert "doc_name" in result.error
        assert result.recoverable is False


# ---------------------------------------------------------------------------
# DocSearchTool: clear action tests
# ---------------------------------------------------------------------------


class TestDocSearchToolClear:
    """Tests for action='clear'."""

    @pytest.mark.asyncio
    async def test_clear_all(self):
        index = VectorIndex()
        await index.index_document("doc1", "Content.", "a.pdf")
        tool = DocSearchTool(vector_index=index)
        result = await tool.execute(action="clear")
        assert result.success is True
        assert result.data["removed_chunks"] >= 1

    @pytest.mark.asyncio
    async def test_clear_specific_doc_id(self):
        index = VectorIndex()
        await index.index_document("doc1", "Content one.", "a.pdf")
        await index.index_document("doc2", "Content two.", "b.pdf")
        tool = DocSearchTool(vector_index=index)
        result = await tool.execute(action="clear", doc_id="doc1")
        assert result.success is True
        assert result.data["removed_chunks"] >= 1
        assert index.chunk_count > 0

    @pytest.mark.asyncio
    async def test_clear_empty_index(self):
        tool = DocSearchTool()
        result = await tool.execute(action="clear")
        assert result.success is True
        assert result.data["removed_chunks"] == 0


# ---------------------------------------------------------------------------
# DocSearchTool: error handling tests
# ---------------------------------------------------------------------------


class TestDocSearchToolErrorHandling:
    """Tests for exception handling and recoverable/non-recoverable classification."""

    @pytest.mark.asyncio
    async def test_error_result_has_structured_fields(self):
        tool = DocSearchTool()
        result = await tool.execute(action="unknown_action")
        assert result.success is False
        assert isinstance(result.error, str)
        assert len(result.error) > 0
        assert isinstance(result.recoverable, bool)
