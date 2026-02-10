"""Tests for TerminologyAgent

Unit tests covering all four operations (extract, query, update, merge),
JSON parsing from LLM responses, error handling, and registration.
Uses mocked TranslationService to avoid real LLM calls.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from agent.agents.terminology_agent import (
    TerminologyAgent,
    _parse_json_from_llm,
)
from agent.models import GlossaryEntry
from agent.registry import agent_registry
from agent.tools.glossary_store import GlossaryStore
from agent.tools.terminology_tool import TerminologyTool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def tmp_glossary_dir(tmp_path: Path):
    """Provide a temporary directory for glossary storage."""
    glossary_dir = tmp_path / "glossaries"
    glossary_dir.mkdir()
    return glossary_dir


@pytest_asyncio.fixture
async def glossary_store(tmp_glossary_dir: Path):
    """Create a GlossaryStore backed by a temp directory."""
    return GlossaryStore(glossary_dir=tmp_glossary_dir)


@pytest_asyncio.fixture
async def mock_translation_service():
    """Create a mock TranslationService that returns configurable responses."""
    svc = AsyncMock()
    svc.translate = AsyncMock(return_value="[]")
    return svc


@pytest_asyncio.fixture
async def agent(
    glossary_store: GlossaryStore,
    mock_translation_service: AsyncMock,
):
    """Create a TerminologyAgent with injected dependencies."""
    tool = TerminologyTool(glossary_store=glossary_store)
    return TerminologyAgent(
        terminology_tool=tool,
        glossary_store=glossary_store,
        translation_service=mock_translation_service,
    )


# ---------------------------------------------------------------------------
# Tests: Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    """Verify TerminologyAgent is registered in agent_registry."""

    def test_registered_in_registry(self):
        """TerminologyAgent should be registered under its class name."""
        assert agent_registry.get("TerminologyAgent") is TerminologyAgent

    def test_name_property(self, agent: TerminologyAgent):
        """name property should return 'terminology'."""
        assert agent.name == "terminology"

    def test_description_property(self, agent: TerminologyAgent):
        """description property should be non-empty."""
        assert agent.description
        assert isinstance(agent.description, str)


# ---------------------------------------------------------------------------
# Tests: _parse_json_from_llm
# ---------------------------------------------------------------------------


class TestParseJsonFromLlm:
    """Test the JSON parsing helper that handles LLM response quirks."""

    def test_plain_json_array(self):
        raw = '[{"english": "NLP", "chinese": "自然语言处理"}]'
        result = _parse_json_from_llm(raw)
        assert len(result) == 1
        assert result[0]["english"] == "NLP"

    def test_markdown_fenced_json(self):
        raw = '```json\n[{"english": "CNN", "chinese": "卷积神经网络"}]\n```'
        result = _parse_json_from_llm(raw)
        assert len(result) == 1
        assert result[0]["english"] == "CNN"

    def test_markdown_fenced_no_lang(self):
        raw = '```\n[{"english": "RNN", "chinese": "循环神经网络"}]\n```'
        result = _parse_json_from_llm(raw)
        assert len(result) == 1
        assert result[0]["english"] == "RNN"

    def test_json_with_surrounding_text(self):
        raw = 'Here are the terms:\n[{"english": "BERT", "chinese": "BERT模型"}]\nDone.'
        result = _parse_json_from_llm(raw)
        assert len(result) == 1
        assert result[0]["english"] == "BERT"

    def test_empty_array(self):
        assert _parse_json_from_llm("[]") == []

    def test_invalid_json_returns_empty(self):
        assert _parse_json_from_llm("not json at all") == []

    def test_non_array_json_returns_empty(self):
        assert _parse_json_from_llm('{"key": "value"}') == []

    def test_empty_string(self):
        assert _parse_json_from_llm("") == []


# ---------------------------------------------------------------------------
# Tests: extract action
# ---------------------------------------------------------------------------


class TestExtractAction:
    """Test the extract operation that uses LLM to extract terms."""

    @pytest.mark.asyncio
    async def test_extract_basic(
        self,
        agent: TerminologyAgent,
        mock_translation_service: AsyncMock,
    ):
        """Extract should call LLM, parse response, and merge with store."""
        llm_response = json.dumps([
            {"english": "Transformer", "chinese": "Transformer", "keep_english": True},
            {"english": "attention mechanism", "chinese": "注意力机制", "keep_english": False},
        ])
        mock_translation_service.translate.return_value = llm_response

        result = await agent.run({
            "action": "extract",
            "text": "The Transformer model uses attention mechanism.",
            "domain": "nlp",
        })

        assert "glossary" in result
        assert "conflicts" in result
        assert len(result["glossary"]) == 2
        assert result["conflicts"] == []

        # Verify LLM was called
        mock_translation_service.translate.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_empty_text(self, agent: TerminologyAgent):
        """Extract with empty text should return empty results."""
        result = await agent.run({
            "action": "extract",
            "text": "",
            "domain": "nlp",
        })
        assert result == {"glossary": [], "conflicts": []}

    @pytest.mark.asyncio
    async def test_extract_whitespace_only_text(self, agent: TerminologyAgent):
        """Extract with whitespace-only text should return empty results."""
        result = await agent.run({
            "action": "extract",
            "text": "   \n  ",
            "domain": "nlp",
        })
        assert result == {"glossary": [], "conflicts": []}

    @pytest.mark.asyncio
    async def test_extract_llm_returns_no_terms(
        self,
        agent: TerminologyAgent,
        mock_translation_service: AsyncMock,
    ):
        """When LLM returns empty array, result should be empty."""
        mock_translation_service.translate.return_value = "[]"

        result = await agent.run({
            "action": "extract",
            "text": "Some text with no technical terms.",
            "domain": "general",
        })
        assert result == {"glossary": [], "conflicts": []}

    @pytest.mark.asyncio
    async def test_extract_llm_returns_invalid_json(
        self,
        agent: TerminologyAgent,
        mock_translation_service: AsyncMock,
    ):
        """When LLM returns unparseable text, result should be empty."""
        mock_translation_service.translate.return_value = "I cannot extract terms."

        result = await agent.run({
            "action": "extract",
            "text": "Some text.",
            "domain": "general",
        })
        assert result == {"glossary": [], "conflicts": []}

    @pytest.mark.asyncio
    async def test_extract_with_markdown_fenced_response(
        self,
        agent: TerminologyAgent,
        mock_translation_service: AsyncMock,
    ):
        """Extract should handle LLM responses wrapped in markdown fences."""
        llm_response = '```json\n[{"english": "GAN", "chinese": "生成对抗网络"}]\n```'
        mock_translation_service.translate.return_value = llm_response

        result = await agent.run({
            "action": "extract",
            "text": "GAN is a generative model.",
            "domain": "cv",
        })
        assert len(result["glossary"]) == 1
        assert result["glossary"][0]["english"] == "GAN"

    @pytest.mark.asyncio
    async def test_extract_detects_conflicts(
        self,
        agent: TerminologyAgent,
        mock_translation_service: AsyncMock,
        glossary_store: GlossaryStore,
    ):
        """Extract should detect conflicts when existing terms have different translations."""
        # Pre-populate the glossary with an existing term
        await glossary_store.save("nlp", [
            GlossaryEntry(
                english="Transformer",
                chinese="变换器",
                domain="nlp",
                source="manual",
            ),
        ])

        # LLM extracts the same term with a different translation
        llm_response = json.dumps([
            {"english": "Transformer", "chinese": "Transformer模型", "keep_english": True},
        ])
        mock_translation_service.translate.return_value = llm_response

        result = await agent.run({
            "action": "extract",
            "text": "The Transformer architecture...",
            "domain": "nlp",
        })

        assert len(result["conflicts"]) == 1
        assert result["conflicts"][0]["english"] == "Transformer"
        assert result["conflicts"][0]["existing"] == "变换器"
        assert result["conflicts"][0]["incoming"] == "Transformer模型"

        # Existing translation should be preserved (not overwritten)
        glossary = result["glossary"]
        transformer_entry = next(
            e for e in glossary if e["english"].lower() == "transformer"
        )
        assert transformer_entry["chinese"] == "变换器"

    @pytest.mark.asyncio
    async def test_extract_skips_invalid_entries(
        self,
        agent: TerminologyAgent,
        mock_translation_service: AsyncMock,
    ):
        """Extract should skip entries with missing english or chinese fields."""
        llm_response = json.dumps([
            {"english": "BERT", "chinese": "BERT模型"},
            {"english": "", "chinese": "空术语"},  # empty english
            {"english": "GPT", "chinese": ""},  # empty chinese
            "not a dict",  # not a dict
            {"english": "Valid", "chinese": "有效"},
        ])
        mock_translation_service.translate.return_value = llm_response

        result = await agent.run({
            "action": "extract",
            "text": "BERT and GPT are language models.",
            "domain": "nlp",
        })

        # Only BERT and Valid should be extracted
        assert len(result["glossary"]) == 2
        english_terms = {e["english"] for e in result["glossary"]}
        assert "BERT" in english_terms
        assert "Valid" in english_terms

    @pytest.mark.asyncio
    async def test_extract_default_domain(
        self,
        agent: TerminologyAgent,
        mock_translation_service: AsyncMock,
    ):
        """Extract without domain should default to 'general'."""
        llm_response = json.dumps([
            {"english": "API", "chinese": "应用程序接口"},
        ])
        mock_translation_service.translate.return_value = llm_response

        result = await agent.run({
            "action": "extract",
            "text": "The API provides...",
        })

        assert len(result["glossary"]) == 1
        assert result["glossary"][0]["domain"] == "general"


# ---------------------------------------------------------------------------
# Tests: query action
# ---------------------------------------------------------------------------


class TestQueryAction:
    """Test the query operation that delegates to TerminologyTool."""

    @pytest.mark.asyncio
    async def test_query_existing_term(
        self,
        agent: TerminologyAgent,
        glossary_store: GlossaryStore,
    ):
        """Query should find existing terms."""
        await glossary_store.save("nlp", [
            GlossaryEntry(english="BERT", chinese="BERT模型", domain="nlp"),
        ])

        result = await agent.run({
            "action": "query",
            "term": "BERT",
            "domain": "nlp",
        })

        assert "entries" in result
        assert len(result["entries"]) == 1
        assert result["entries"][0]["english"] == "BERT"

    @pytest.mark.asyncio
    async def test_query_nonexistent_term(
        self,
        agent: TerminologyAgent,
    ):
        """Query for a non-existent term should return empty entries."""
        result = await agent.run({
            "action": "query",
            "term": "nonexistent",
            "domain": "nlp",
        })

        assert "entries" in result
        assert len(result["entries"]) == 0

    @pytest.mark.asyncio
    async def test_query_fuzzy_match(
        self,
        agent: TerminologyAgent,
        glossary_store: GlossaryStore,
    ):
        """Query should support fuzzy matching (substring)."""
        await glossary_store.save("nlp", [
            GlossaryEntry(english="attention mechanism", chinese="注意力机制", domain="nlp"),
        ])

        result = await agent.run({
            "action": "query",
            "term": "attention",
            "domain": "nlp",
        })

        assert len(result["entries"]) == 1
        assert result["entries"][0]["english"] == "attention mechanism"


# ---------------------------------------------------------------------------
# Tests: update action
# ---------------------------------------------------------------------------


class TestUpdateAction:
    """Test the update operation that delegates to TerminologyTool."""

    @pytest.mark.asyncio
    async def test_update_new_term(
        self,
        agent: TerminologyAgent,
        glossary_store: GlossaryStore,
    ):
        """Update should add a new term to the glossary."""
        result = await agent.run({
            "action": "update",
            "domain": "nlp",
            "english": "Transformer",
            "chinese": "Transformer模型",
            "source": "user_edit",
        })

        assert result == {"updated": True}

        # Verify the term was saved
        entries = await glossary_store.load("nlp")
        assert len(entries) == 1
        assert entries[0].english == "Transformer"
        assert entries[0].chinese == "Transformer模型"

    @pytest.mark.asyncio
    async def test_update_existing_term(
        self,
        agent: TerminologyAgent,
        glossary_store: GlossaryStore,
    ):
        """Update should modify an existing term's translation."""
        await glossary_store.save("nlp", [
            GlossaryEntry(english="BERT", chinese="BERT", domain="nlp"),
        ])

        result = await agent.run({
            "action": "update",
            "domain": "nlp",
            "english": "BERT",
            "chinese": "BERT模型",
        })

        assert result == {"updated": True}

        entries = await glossary_store.load("nlp")
        assert len(entries) == 1
        assert entries[0].chinese == "BERT模型"


# ---------------------------------------------------------------------------
# Tests: merge action
# ---------------------------------------------------------------------------


class TestMergeAction:
    """Test the merge operation that delegates to TerminologyTool."""

    @pytest.mark.asyncio
    async def test_merge_new_entries(
        self,
        agent: TerminologyAgent,
        glossary_store: GlossaryStore,
    ):
        """Merge should add new entries to the glossary."""
        result = await agent.run({
            "action": "merge",
            "domain": "nlp",
            "entries": [
                {"english": "BERT", "chinese": "BERT模型", "domain": "nlp"},
                {"english": "GPT", "chinese": "GPT模型", "domain": "nlp"},
            ],
        })

        assert "conflicts" in result
        assert "merged_count" in result
        assert result["merged_count"] == 2
        assert result["conflicts"] == []

    @pytest.mark.asyncio
    async def test_merge_with_conflicts(
        self,
        agent: TerminologyAgent,
        glossary_store: GlossaryStore,
    ):
        """Merge should detect conflicts when translations differ."""
        await glossary_store.save("nlp", [
            GlossaryEntry(english="BERT", chinese="BERT", domain="nlp"),
        ])

        result = await agent.run({
            "action": "merge",
            "domain": "nlp",
            "entries": [
                {"english": "BERT", "chinese": "BERT模型", "domain": "nlp"},
            ],
        })

        assert len(result["conflicts"]) == 1
        assert result["conflicts"][0]["english"] == "BERT"
        assert result["conflicts"][0]["existing"] == "BERT"
        assert result["conflicts"][0]["incoming"] == "BERT模型"


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Test error handling for invalid inputs."""

    @pytest.mark.asyncio
    async def test_invalid_input_type(self, agent: TerminologyAgent):
        """Non-dict input should raise ValueError."""
        with pytest.raises(ValueError, match="must be a dict"):
            await agent.run("not a dict")

    @pytest.mark.asyncio
    async def test_missing_action(self, agent: TerminologyAgent):
        """Missing action field should raise ValueError."""
        with pytest.raises(ValueError, match="Missing required field: action"):
            await agent.run({})

    @pytest.mark.asyncio
    async def test_unknown_action(self, agent: TerminologyAgent):
        """Unknown action should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown action"):
            await agent.run({"action": "delete"})

    @pytest.mark.asyncio
    async def test_callable_interface(
        self,
        agent: TerminologyAgent,
        mock_translation_service: AsyncMock,
    ):
        """Agent should work via __call__ (setup -> run -> teardown)."""
        mock_translation_service.translate.return_value = "[]"

        result = await agent({"action": "extract", "text": "test", "domain": "test"})
        assert result == {"glossary": [], "conflicts": []}
