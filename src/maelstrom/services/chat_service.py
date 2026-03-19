from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from maelstrom.db import chat_repo
from maelstrom.db.database import get_db
from maelstrom.services.llm_config_service import get_config
from maelstrom.services.paperqa_service import PaperQAError, PaperQAService

_paperqa_service = PaperQAService()

# In-memory store for pending/running QA tasks
_qa_tasks: dict[str, dict] = {}


async def start_ask(session_id: str, question: str) -> str:
    """Start a QA task. Returns msg_id."""
    msg_id = str(uuid.uuid4())
    _qa_tasks[msg_id] = {
        "session_id": session_id,
        "question": question,
        "status": "pending",
        "tokens": [],
        "answer": None,
        "citations": [],
        "error": None,
    }
    # Launch background task
    asyncio.create_task(_run_qa(msg_id))
    return msg_id


async def _run_qa(msg_id: str) -> None:
    task = _qa_tasks[msg_id]
    task["status"] = "running"
    try:
        config = get_config()
        profile = config.get_active_profile_or_raise()
        settings = _paperqa_service.build_settings(profile, config.embedding)
        result = await _paperqa_service.ask(task["question"], settings)
        task["answer"] = result.get("answer", "")
        task["citations"] = result.get("citations", [])
        task["status"] = "done"

        # Persist to DB
        db = await get_db()
        await chat_repo.create_chat_message(
            db, task["session_id"], "user", task["question"]
        )
        await chat_repo.create_chat_message(
            db, task["session_id"], "assistant", task["answer"],
            citations_json=json.dumps(task["citations"]),
        )
    except PaperQAError as e:
        task["error"] = str(e)
        task["status"] = "error"
    except Exception as e:
        task["error"] = str(e)
        task["status"] = "error"


async def stream_answer(msg_id: str) -> AsyncGenerator[dict, None]:
    """Yield SSE events for a QA task."""
    task = _qa_tasks.get(msg_id)
    if not task:
        yield {"event": "error", "data": json.dumps({"message": "Task not found"})}
        return

    # Wait for completion
    while task["status"] in ("pending", "running"):
        await asyncio.sleep(0.1)

    if task["status"] == "error":
        yield {"event": "error", "data": json.dumps({"message": task["error"]})}
        return

    # Simulate token streaming from completed answer
    answer = task["answer"] or ""
    words = answer.split(" ")
    for word in words:
        token = word + " "
        yield {"event": "chat_token", "data": json.dumps({"token": token})}

    yield {
        "event": "chat_done",
        "data": json.dumps({
            "answer": answer,
            "citations": task["citations"],
        }),
    }


def get_task(msg_id: str) -> dict | None:
    return _qa_tasks.get(msg_id)
