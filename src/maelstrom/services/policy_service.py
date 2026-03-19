"""Policy service — get/update governance policy per session."""
from __future__ import annotations

import json

import aiosqlite

from maelstrom.db import policy_repo
from maelstrom.schemas.policy import PolicyConfig


async def get_policy_config(db: aiosqlite.Connection, session_id: str) -> PolicyConfig:
    row = await policy_repo.get_policy(db, session_id)
    if not row:
        return PolicyConfig()  # defaults
    return PolicyConfig(**json.loads(row["config_json"]))


async def update_policy_config(
    db: aiosqlite.Connection, session_id: str, config: PolicyConfig,
) -> PolicyConfig:
    await policy_repo.upsert_policy(db, session_id, config.model_dump_json())
    return config
