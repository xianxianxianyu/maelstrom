from fastapi import APIRouter
from app.services.providers.glm import GLMProvider
from app.services.providers.openai import OpenAIProvider
from app.services.providers.deepseek import DeepSeekProvider

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("/")
async def get_available_models():
    """Get all available models from all providers"""
    from app.services.providers.base import ModelInfo

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
