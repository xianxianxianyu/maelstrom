from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from maelstrom.db import artifact_repo, session_repo
from maelstrom.db.database import get_db
from maelstrom.services.llm_config_service import get_config
from maelstrom.services.paperqa_service import PaperQAError, PaperQAService

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "pdfs")
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

_paperqa_service = PaperQAService()


async def save_and_index(session_id: str, filename: str, content: bytes) -> dict:
    if not filename.lower().endswith(".pdf"):
        raise ValueError("Only PDF files are accepted")
    if len(content) > MAX_FILE_SIZE:
        raise OverflowError(f"File exceeds {MAX_FILE_SIZE // (1024*1024)}MB limit")

    # Save to disk
    session_dir = os.path.join(DATA_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    file_path = os.path.join(session_dir, filename)
    with open(file_path, "wb") as f:
        f.write(content)

    # Index with paper-qa
    config = get_config()
    profile = config.get_active_profile_or_raise()
    settings = _paperqa_service.build_settings(profile, config.embedding)
    try:
        doc_id = await _paperqa_service.index_document(file_path, settings)
    except PaperQAError:
        # Clean up file on index failure
        if os.path.exists(file_path):
            os.unlink(file_path)
        raise

    # Persist metadata
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    import json

    meta = json.dumps({"filename": filename, "file_path": file_path, "doc_id": doc_id})
    artifact = await artifact_repo.create_artifact(db, session_id, "indexed_doc", meta)
    await session_repo.touch_session(db, session_id)

    return {
        "doc_id": artifact["id"],
        "filename": filename,
        "indexed_at": now,
    }


async def list_docs(session_id: str) -> list[dict]:
    import json

    db = await get_db()
    artifacts = await artifact_repo.list_artifacts_by_type(db, session_id, "indexed_doc")
    results = []
    for a in artifacts:
        data = json.loads(a["data_json"])
        results.append({
            "doc_id": a["id"],
            "filename": data.get("filename", ""),
            "indexed_at": a["created_at"],
        })
    return results


async def delete_doc(doc_id: str) -> bool:
    import json

    db = await get_db()
    artifact = await artifact_repo.get_artifact(db, doc_id)
    if not artifact:
        return False
    # Remove file
    data = json.loads(artifact["data_json"])
    file_path = data.get("file_path", "")
    if file_path and os.path.exists(file_path):
        os.unlink(file_path)
    # Remove DB record
    await db.execute("DELETE FROM artifacts WHERE id = ?", (doc_id,))
    await db.commit()
    # Touch session so updated_at reflects this activity
    sid = artifact.get("session_id")
    if sid:
        await session_repo.touch_session(db, sid)
    return True


async def share_papers_to_qa(session_id: str, papers: list[dict]) -> dict:
    """Share Gap Engine papers (with pdf_url) to QA Chat index.

    Downloads PDFs and indexes them. Returns summary of results.
    """
    import json
    import httpx
    import logging

    logger = logging.getLogger(__name__)
    shared = 0
    failed = 0
    skipped = 0

    for paper in papers:
        pdf_url = paper.get("pdf_url")
        if not pdf_url:
            skipped += 1
            continue

        title = paper.get("title", "paper")
        filename = f"{title[:60].replace('/', '_')}.pdf"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(pdf_url)
                resp.raise_for_status()
                content = resp.content

            session_dir = os.path.join(DATA_DIR, session_id)
            os.makedirs(session_dir, exist_ok=True)
            file_path = os.path.join(session_dir, filename)
            with open(file_path, "wb") as f:
                f.write(content)

            config = get_config()
            profile = config.get_active_profile_or_raise()
            settings = _paperqa_service.build_settings(profile, config.embedding)
            doc_id = await _paperqa_service.index_document(file_path, settings)

            db = await get_db()
            meta = json.dumps({"filename": filename, "file_path": file_path,
                               "doc_id": doc_id, "paper_id": paper.get("paper_id", "")})
            await artifact_repo.create_artifact(db, session_id, "indexed_doc", meta)
            shared += 1
        except Exception as e:
            logger.warning("Failed to share paper %s: %s", title, e)
            failed += 1

    db = await get_db()
    await session_repo.touch_session(db, session_id)

    return {"shared": shared, "failed": failed, "skipped": skipped}
