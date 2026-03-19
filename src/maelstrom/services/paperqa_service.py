from __future__ import annotations

from typing import Any


class PaperQAError(Exception):
    """Wrapper for paper-qa exceptions."""


class PaperQAService:
    """Thin adapter around paper-qa, isolating its API from the rest of the app."""

    def build_settings(self, profile: Any, embedding: Any = None) -> Any:
        """Build paper-qa Settings from an LLMProfile and optional EmbeddingConfig."""
        from paperqa import Settings

        protocol = profile.protocol if hasattr(profile, "protocol") else profile.get("protocol", "openai_chat")
        model = profile.model if hasattr(profile, "model") else profile.get("model", "gpt-4o")
        temperature = profile.temperature if hasattr(profile, "temperature") else profile.get("temperature", 0.7)
        base_url = profile.base_url if hasattr(profile, "base_url") else profile.get("base_url")

        # Map protocol to litellm model string
        if protocol == "anthropic_messages":
            llm_str = f"anthropic/{model}"
        else:
            llm_str = model

        llm_cfg: dict[str, Any] = {}
        if base_url:
            llm_cfg["base_url"] = base_url

        # Embedding config
        if embedding:
            embedding_str = embedding.model if hasattr(embedding, "model") else embedding.get("model", "text-embedding-3-small")
        else:
            embedding_str = "text-embedding-3-small"

        settings = Settings(
            llm=llm_str,
            llm_config=llm_cfg or None,
            summary_llm=llm_str,
            summary_llm_config=llm_cfg or None,
            embedding=embedding_str,
            temperature=temperature,
        )
        return settings

    async def index_document(self, file_path: str, settings: Any) -> str:
        """Index a single PDF. Returns a doc identifier."""
        try:
            from paperqa import Docs

            docs = Docs()
            await docs.aadd(file_path, settings=settings)
            return file_path
        except Exception as e:
            raise PaperQAError(f"Failed to index document: {e}") from e

    async def ask(self, question: str, settings: Any) -> dict:
        """Ask a question. Returns answer dict with text and citations."""
        try:
            from paperqa import ask as pqa_ask

            result = await pqa_ask(question, settings=settings)
            return {
                "answer": result.answer if hasattr(result, "answer") else str(result),
                "citations": [],
            }
        except Exception as e:
            raise PaperQAError(f"Failed to ask question: {e}") from e
