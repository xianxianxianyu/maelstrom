"""normalize_dedup node — cross-source deduplication of papers."""
from __future__ import annotations

import logging
from typing import Any

from maelstrom.graph.gap_engine import GapEngineState

logger = logging.getLogger(__name__)

_TITLE_SIMILARITY_THRESHOLD = 0.92


def _levenshtein_ratio(a: str, b: str) -> float:
    """Compute Levenshtein similarity ratio between two strings."""
    try:
        from Levenshtein import ratio
        return ratio(a, b)
    except ImportError:
        # Fallback: simple ratio based on difflib
        from difflib import SequenceMatcher
        return SequenceMatcher(None, a, b).ratio()


def _first_author_surname(paper: dict) -> str:
    """Extract first author's surname (lowercased)."""
    authors = paper.get("authors", [])
    if not authors:
        return ""
    name = authors[0] if isinstance(authors[0], str) else authors[0].get("name", "")
    parts = name.strip().split()
    return parts[-1].lower() if parts else ""


def _richness_score(paper: dict) -> int:
    """Count non-empty fields as a proxy for metadata richness."""
    score = 0
    for key in ("title", "abstract", "year", "venue", "doi", "pdf_url", "citation_count"):
        val = paper.get(key)
        if val is not None and val != "" and val != 0:
            score += 1
    authors = paper.get("authors", [])
    if authors:
        score += 1
    ext = paper.get("external_ids", {})
    score += sum(1 for v in ext.values() if v is not None)
    return score
def _merge_external_ids(target: dict, source: dict) -> dict:
    """Merge external_ids from source into target, keeping non-None values."""
    merged = dict(target)
    for k, v in source.items():
        if v is not None and merged.get(k) is None:
            merged[k] = v
    return merged


def normalize_dedup(state: GapEngineState) -> GapEngineState:
    """Cross-source deduplication of raw_papers."""
    state["current_step"] = "normalize_dedup"
    raw_papers: list[dict] = state.get("raw_papers", [])

    if not raw_papers:
        state["papers"] = []
        return state

    # Index for dedup: map canonical key → index in deduped list
    deduped: list[dict] = []
    doi_index: dict[str, int] = {}
    s2_index: dict[str, int] = {}
    corpus_index: dict[str, int] = {}

    for paper in raw_papers:
        ext = paper.get("external_ids", {})
        doi = ext.get("doi") or paper.get("doi")
        s2_id = ext.get("s2_id")
        corpus_id = ext.get("corpus_id")

        # Try DOI match
        if doi and doi in doi_index:
            idx = doi_index[doi]
            deduped[idx] = _pick_and_merge(deduped[idx], paper)
            continue

        # Try S2 ID match
        if s2_id and s2_id in s2_index:
            idx = s2_index[s2_id]
            deduped[idx] = _pick_and_merge(deduped[idx], paper)
            continue

        # Try Corpus ID match
        if corpus_id and corpus_id in corpus_index:
            idx = corpus_index[corpus_id]
            deduped[idx] = _pick_and_merge(deduped[idx], paper)
            continue

        # Try title fuzzy match
        title = (paper.get("title") or "").lower().strip()
        surname = _first_author_surname(paper)
        matched = False
        if title:
            for i, existing in enumerate(deduped):
                ex_title = (existing.get("title") or "").lower().strip()
                if not ex_title:
                    continue
                sim = _levenshtein_ratio(title, ex_title)
                if sim >= _TITLE_SIMILARITY_THRESHOLD:
                    ex_surname = _first_author_surname(existing)
                    if surname and ex_surname and surname == ex_surname:
                        deduped[i] = _pick_and_merge(deduped[i], paper)
                        matched = True
                        break
            if matched:
                continue

        # No match — add as new
        idx = len(deduped)
        deduped.append(paper)
        if doi:
            doi_index[doi] = idx
        if s2_id:
            s2_index[s2_id] = idx
        if corpus_id:
            corpus_index[corpus_id] = idx

    state["papers"] = deduped
    return state


def _pick_and_merge(existing: dict, incoming: dict) -> dict:
    """Keep the richer record, merge external_ids from both."""
    if _richness_score(incoming) > _richness_score(existing):
        winner, loser = dict(incoming), existing
    else:
        winner, loser = dict(existing), incoming

    ext_w = winner.get("external_ids", {})
    ext_l = loser.get("external_ids", {})
    winner["external_ids"] = _merge_external_ids(ext_w, ext_l)
    return winner
