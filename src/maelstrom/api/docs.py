from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from maelstrom.db.database import get_db
from maelstrom.db import session_repo
from maelstrom.services import doc_service
from maelstrom.services.paperqa_service import PaperQAError

router = APIRouter(prefix="/api/chat/docs", tags=["docs"])


@router.post("/upload", status_code=201)
async def upload_doc(file: UploadFile = File(...), session_id: str = Form(...)):
    db = await get_db()
    session = await session_repo.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    content = await file.read()

    try:
        result = await doc_service.save_and_index(session_id, file.filename or "upload.pdf", content)
    except ValueError:
        raise HTTPException(status_code=415, detail="Only PDF files are accepted")
    except OverflowError:
        raise HTTPException(status_code=413, detail="File too large (max 50MB)")
    except PaperQAError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return result


@router.get("")
async def list_docs(session_id: str):
    return await doc_service.list_docs(session_id)


@router.delete("/{doc_id}", status_code=204)
async def delete_doc(doc_id: str):
    deleted = await doc_service.delete_doc(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
