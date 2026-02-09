from pydantic import BaseModel, ConfigDict
from typing import Optional, Literal


class ProviderModel(BaseModel):
    """Model selection for translation"""
    provider: Literal["zhipuai", "openai", "deepseek"]
    model: str
    api_key: Optional[str] = None


class TranslationRequest(BaseModel):
    """Request with model configuration"""
    provider_model: ProviderModel


class TranslationResponse(BaseModel):
    """Translation result"""
    model_config = ConfigDict(protected_namespaces=())

    markdown: str
    ocr_markdown: Optional[str] = None
    provider_used: str
    model_used: str


class ModelInfoResponse(BaseModel):
    """Available model information"""
    id: str
    name: str
    provider: str
    description: str
