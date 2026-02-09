from fastapi import APIRouter
from core.providers.glm import GLMProvider
from core.providers.openai import OpenAIProvider
from core.providers.deepseek import DeepSeekProvider

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("/")
async def get_available_models():
    """Get all available models from all providers"""
    from core.providers.base import ModelInfo

    models: list[ModelInfo] = []
    models.extend(GLMProvider.AVAILABLE_MODELS)
    models.extend(OpenAIProvider.AVAILABLE_MODELS)
    models.extend(DeepSeekProvider.AVAILABLE_MODELS)

    return {
        "models": [
            {
                "id": m.id,
                "name": m.name,
                "provider": m.provider,
                "description": m.description
            }
            for m in models
        ]
    }
