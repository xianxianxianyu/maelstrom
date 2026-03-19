"""Gap followup service — enrich QA questions with EvidenceMemory context."""
from __future__ import annotations

import logging

from maelstrom.services.evidence_memory import get_evidence_memory

logger = logging.getLogger(__name__)


async def enrich_gap_followup(
    session_id: str,
    user_input: str,
    gap_ref: str | None = None,
) -> str:
    """Enrich a gap followup question with context from EvidenceMemory."""
    mem = get_evidence_memory()

    hits = []
    try:
        if gap_ref:
            # Try exact source_id match first, then FTS
            hits = await mem.search_by_source_id(session_id, gap_ref)
            if not hits:
                hits = await mem.search(session_id, gap_ref, limit=5)
        else:
            hits = await mem.search(session_id, user_input, limit=5)
    except Exception as e:
        logger.warning("EvidenceMemory search failed: %s", e)
        return user_input

    if not hits:
        return user_input

    context_parts = []
    for hit in hits:
        context_parts.append(f"[{hit.source_type}] {hit.title}: {hit.snippet}")

    enriched = (
        "基于以下已有研究上下文：\n"
        + "\n".join(context_parts)
        + f"\n\n用户问题：{user_input}"
    )
    return enriched
