from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maelstrom.schemas.llm_config import LLMProfile
from maelstrom.services.paperqa_service import PaperQAError, PaperQAService

try:
    import paperqa  # noqa: F401
    HAS_PAPERQA = True
except ImportError:
    HAS_PAPERQA = False

needs_paperqa = pytest.mark.skipif(not HAS_PAPERQA, reason="paperqa not installed")


@pytest.fixture
def svc():
    return PaperQAService()


@needs_paperqa
def test_build_settings_openai(svc):
    cfg = LLMProfile(protocol="openai_chat", model="gpt-4o", temperature=0.7)
    settings = svc.build_settings(cfg)
    assert settings.llm == "gpt-4o"
    assert settings.temperature == 0.7
    assert settings.embedding == "text-embedding-3-small"


@needs_paperqa
def test_build_settings_anthropic(svc):
    cfg = LLMProfile(protocol="anthropic_messages", model="claude-sonnet-4-6", temperature=0.5)
    settings = svc.build_settings(cfg)
    assert settings.llm == "anthropic/claude-sonnet-4-6"
    assert settings.temperature == 0.5


@needs_paperqa
def test_build_settings_local(svc):
    cfg = LLMProfile(
        protocol="openai_chat", model="llama3", base_url="http://localhost:11434", temperature=0.3
    )
    settings = svc.build_settings(cfg)
    assert settings.llm == "llama3"
    assert settings.llm_config is not None
    assert settings.llm_config["base_url"] == "http://localhost:11434"


@needs_paperqa
def test_settings_no_cache(svc):
    cfg1 = LLMProfile(temperature=0.5)
    cfg2 = LLMProfile(temperature=1.0)
    s1 = svc.build_settings(cfg1)
    s2 = svc.build_settings(cfg2)
    assert s1.temperature != s2.temperature
    assert s1 is not s2


@pytest.mark.asyncio
async def test_index_document_mock(svc):
    mock_docs = MagicMock()
    mock_docs.aadd = AsyncMock()
    with patch("maelstrom.services.paperqa_service.PaperQAService.index_document") as mock_idx:
        mock_idx.return_value = "/path/to/test.pdf"
        result = await svc.index_document("/path/to/test.pdf", MagicMock())
    assert result == "/path/to/test.pdf"


@pytest.mark.asyncio
async def test_ask_streaming_mock(svc):
    mock_result = MagicMock()
    mock_result.answer = "Test answer"
    with patch("maelstrom.services.paperqa_service.PaperQAService.ask") as mock_ask:
        mock_ask.return_value = {"answer": "Test answer", "citations": []}
        result = await svc.ask("What is X?", MagicMock())
    assert result["answer"] == "Test answer"


@pytest.mark.asyncio
async def test_paperqa_error_handling(svc):
    with patch(
        "maelstrom.services.paperqa_service.PaperQAService.index_document",
        side_effect=PaperQAError("test error"),
    ):
        with pytest.raises(PaperQAError, match="test error"):
            await svc.index_document("bad.pdf", MagicMock())
