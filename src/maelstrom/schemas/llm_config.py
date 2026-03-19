from __future__ import annotations

from pydantic import BaseModel, Field

from .common import ProtocolEnum


class LLMProfile(BaseModel):
    name: str = Field(default="Default", description="Display name for this profile")
    protocol: ProtocolEnum = Field(
        default=ProtocolEnum.openai_chat, description="Message protocol"
    )
    base_url: str = Field(
        default="https://api.openai.com/v1", description="API endpoint base URL"
    )
    api_key: str | None = Field(default=None, description="API key (optional for local models)")
    model: str = Field(default="gpt-4o", description="Model identifier")
    temperature: float = Field(default=0.7, ge=0, le=2, description="Sampling temperature")
    max_tokens: int = Field(default=4096, gt=0, description="Max output tokens")


class EmbeddingConfig(BaseModel):
    model: str = Field(default="text-embedding-3-small", description="Embedding model name")
    api_key: str | None = Field(
        default=None, description="Embedding API key (falls back to active profile key)"
    )
    base_url: str | None = Field(default=None, description="Embedding endpoint URL")


class ModelSlot(BaseModel):
    """A single model configuration slot (QA, script, image, video)."""
    provider: str = Field(default="openai", description="Provider: openai | anthropic | ollama | custom")
    model: str = Field(default="", description="Model identifier")
    api_key: str = Field(default="", description="API key")
    base_url: str = Field(default="", description="Custom endpoint URL")
    temperature: float = Field(default=0.7, ge=0, le=2, description="Sampling temperature")
    max_tokens: int = Field(default=4096, gt=0, description="Max output tokens")


class AppSettings(BaseModel):
    """Multi-slot model settings persisted in SQLite."""
    qa_model: ModelSlot = Field(default_factory=ModelSlot, description="QA chat model")
    script_model: ModelSlot = Field(default_factory=ModelSlot, description="Script/outline generation model")
    image_model: ModelSlot = Field(default_factory=ModelSlot, description="Image generation model (Flux, DALL-E, SD)")
    video_model: ModelSlot = Field(default_factory=ModelSlot, description="Video generation model (Runway, Kling, Sora)")


class MaelstromConfig(BaseModel):
    profiles: dict[str, LLMProfile] = Field(default_factory=dict)
    active_profile: str = Field(default="default")
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)

    def get_active_profile(self) -> LLMProfile | None:
        return self.profiles.get(self.active_profile)

    def get_active_profile_or_raise(self) -> LLMProfile:
        profile = self.get_active_profile()
        if profile is None:
            raise ValueError(f"Active profile '{self.active_profile}' not found")
        return profile
