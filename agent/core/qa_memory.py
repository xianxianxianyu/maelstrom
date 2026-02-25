from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class QATurn:
    role: str
    content: str
    doc_id: Optional[str]


class QASessionMemory:
    def __init__(self, max_turns: int = 8) -> None:
        self.max_turns = max_turns
        self._sessions: Dict[str, List[QATurn]] = {}

    def get_context(self, session_id: str, doc_id: Optional[str]) -> List[QATurn]:
        turns = self._sessions.get(session_id, [])
        if doc_id is None:
            return turns[-self.max_turns :]
        return [turn for turn in turns if turn.doc_id == doc_id][-self.max_turns :]

    def append(self, session_id: str, role: str, content: str, doc_id: Optional[str]) -> None:
        turns = self._sessions.setdefault(session_id, [])
        turns.append(QATurn(role=role, content=content, doc_id=doc_id))
        if len(turns) > self.max_turns * 2:
            self._sessions[session_id] = turns[-self.max_turns * 2 :]


qa_session_memory = QASessionMemory()
