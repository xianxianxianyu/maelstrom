"""targeted_retrieval node — EvidenceMemory + incremental PaperRetriever search."""
from __future__ import annotations

import json
import logging
from typing import Any

from maelstrom.services.evidence_memory import get_evidence_memory
from maelstrom.services.llm_client import call_llm

logger = logging.getLogger(__name__)

_QUERY_PROMPT = """You are an academic research assistant. Given a research topic or gap description, generate 2-3 precise search queries for finding highly relevant papers. Focus on specific methods, datasets, and limitations.

Topic: {topic}
{gap_context}

Return ONLY a JSON array of strings. Example: ["query 1", "query 2"]"""


async def _generate_queries(topic: str, gap_info: dict | None, llm_config: dict) -> list[str]:
    queries = [topic]
    gap_context = ""
    if gap_info:
        gap_context = f"Gap title: {gap_info.get('title', '')}\nGap summary: {gap_info.get('summary', '')}"
    try:
        prompt = _QUERY_PROMPT.format(topic=topic, gap_context=gap_context)
        raw = await call_llm(prompt, llm_config, max_tokens=512, timeout=15.0)
        parsed = json.loads(raw.strip())
        if isinstance(parsed, list):
            for q in parsed:
                q_str = str(q).strip()
                if q_str and q_str != topic and q_str not in queries:
                    queries.append(q_str)
    except Exception as e:
        logger.warning("Targeted query generation failed, using topic only: %s", e)
    return queries


async def targeted_retrieval(state: dict) -> dict:
    state["current_step"] = "targeted_retrieval"
    session_id = state.get("session_id", "")
    topic = state.get("topic", "")
    gap_info = state.get("gap_info")
    llm_config = state.get("llm_config", {})

    # Load gap run results when source_gap_id is provided
    source_gap_id = state.get("source_gap_id")
    if source_gap_id and not gap_info:
        try:
            from maelstrom.db import gap_run_repo
            from maelstrom.db.database import get_db
            db = await get_db()
            gap_run = await gap_run_repo.get_gap_run(db, source_gap_id)
            if gap_run and gap_run.get("result_json"):
                import json as _json
                gap_result = _json.loads(gap_run["result_json"])
                gap_info = {
                    "title": gap_run.get("topic", ""),
                    "summary": ", ".join(
                        g.get("title", "") for g in gap_result.get("ranked_gaps", [])[:5]
                    ),
                    "ranked_gaps": gap_result.get("ranked_gaps", []),
                }
                state["gap_info"] = gap_info
        except Exception as e:
            logger.warning("Failed to load gap run %s: %s", source_gap_id, e)

    # 1. Read existing papers from EvidenceMemory
    existing_paper_ids: set[str] = set()
    existing_papers: list[dict[str, Any]] = []
    try:
        mem = get_evidence_memory()
        hits = await mem.search(session_id, topic, limit=20)
        for h in hits:
            if h.source_type == "paper" and h.source_id not in existing_paper_ids:
                existing_paper_ids.add(h.source_id)
                existing_papers.append({"paper_id": h.source_id, "title": h.title, "abstract": h.snippet})
    except Exception as e:
        logger.warning("EvidenceMemory read failed: %s", e)

    # 2. Generate targeted queries
    queries = await _generate_queries(topic, gap_info, llm_config)
    state["targeted_queries"] = queries

    # 3. Incremental retrieval via PaperRetriever
    new_papers: list[dict[str, Any]] = []
    retriever = state.get("_retriever")
    if retriever:
        for query in queries:
            try:
                results = await retriever.search(query, max_results=10)
                for p in results:
                    pid = p.paper_id if hasattr(p, "paper_id") else p.get("paper_id", "")
                    if pid and pid not in existing_paper_ids:
                        existing_paper_ids.add(pid)
                        paper_dict = p.model_dump() if hasattr(p, "model_dump") else p
                        new_papers.append(paper_dict)
            except Exception as e:
                logger.warning("Retrieval failed for query '%s': %s", query, e)

    # 4. Ingest new papers into EvidenceMemory
    if new_papers:
        try:
            mem = get_evidence_memory()
            for p in new_papers:
                await mem.ingest_text(
                    session_id, "paper", p.get("paper_id", ""),
                    p.get("title", ""), p.get("abstract", ""),
                )
        except Exception as e:
            logger.warning("EvidenceMemory ingest failed: %s", e)

    # 5. Merge
    all_papers = existing_papers + new_papers
    state["targeted_papers"] = all_papers
    return state
