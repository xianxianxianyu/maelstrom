"""Artifacts API — view any research artifact by ID."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from maelstrom.db import artifact_repo
from maelstrom.db.database import get_db

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


@router.get("")
async def list_artifacts(session_id: str, type: str | None = None):
    db = await get_db()
    if type:
        artifacts = await artifact_repo.list_artifacts_by_type(db, session_id, type)
    else:
        artifacts = await artifact_repo.list_artifacts_by_session(db, session_id)
    results = []
    for a in artifacts:
        item = {
            "id": a["id"],
            "session_id": a["session_id"],
            "type": a["type"],
            "created_at": a["created_at"],
        }
        try:
            item["data"] = json.loads(a["data_json"])
        except (json.JSONDecodeError, TypeError):
            item["data"] = {}
        results.append(item)
    return results


@router.get("/{artifact_id}")
async def get_artifact(artifact_id: str):
    db = await get_db()
    artifact = await artifact_repo.get_artifact(db, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    result = {
        "id": artifact["id"],
        "session_id": artifact["session_id"],
        "type": artifact["type"],
        "created_at": artifact["created_at"],
    }
    try:
        result["data"] = json.loads(artifact["data_json"])
    except (json.JSONDecodeError, TypeError):
        result["data"] = {}
    return result
