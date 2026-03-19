from fastapi import APIRouter

from maelstrom.schemas.llm_config import AppSettings
from maelstrom.services.settings_service import get_app_settings, update_app_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=AppSettings)
async def get_settings():
    return await get_app_settings(masked=True)


@router.put("", response_model=AppSettings)
async def put_settings(settings: AppSettings):
    return await update_app_settings(settings)
