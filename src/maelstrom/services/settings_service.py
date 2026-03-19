"""Service for reading/writing multi-slot model settings in SQLite."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from maelstrom.db.database import get_db
from maelstrom.schemas.llm_config import AppSettings, ModelSlot

SETTINGS_KEY = "model_slots"


def _mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return key
    return key[:3] + "***" + key[-4:]


def _is_masked(key: str) -> bool:
    return "***" in key


def _mask_slot(slot: ModelSlot) -> ModelSlot:
    return slot.model_copy(update={"api_key": _mask_key(slot.api_key)})


def _mask_settings(settings: AppSettings) -> AppSettings:
    return settings.model_copy(update={
        "qa_model": _mask_slot(settings.qa_model),
        "script_model": _mask_slot(settings.script_model),
        "image_model": _mask_slot(settings.image_model),
        "video_model": _mask_slot(settings.video_model),
    })


def _merge_slot_key(new_slot: ModelSlot, old_slot: ModelSlot) -> ModelSlot:
    """If the incoming api_key is masked, keep the original."""
    api_key = new_slot.api_key
    if api_key and _is_masked(api_key):
        api_key = old_slot.api_key
    return new_slot.model_copy(update={"api_key": api_key})


async def get_app_settings(masked: bool = True) -> AppSettings:
    db = await get_db()
    row = await db.execute(
        "SELECT value_json FROM app_settings WHERE key = ?", (SETTINGS_KEY,)
    )
    row = await row.fetchone()
    if row:
        settings = AppSettings.model_validate(json.loads(row["value_json"]))
    else:
        settings = AppSettings()
    return _mask_settings(settings) if masked else settings


async def update_app_settings(new_settings: AppSettings) -> AppSettings:
    old = await get_app_settings(masked=False)
    merged = new_settings.model_copy(update={
        "qa_model": _merge_slot_key(new_settings.qa_model, old.qa_model),
        "script_model": _merge_slot_key(new_settings.script_model, old.script_model),
        "image_model": _merge_slot_key(new_settings.image_model, old.image_model),
        "video_model": _merge_slot_key(new_settings.video_model, old.video_model),
    })
    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    await db.execute(
        """INSERT INTO app_settings (key, value_json, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at""",
        (SETTINGS_KEY, merged.model_dump_json(), now),
    )
    await db.commit()
    return _mask_settings(merged)
