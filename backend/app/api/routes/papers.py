import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.paper_repository_service import get_paper_repository

router = APIRouter(prefix="/api/papers", tags=["papers"])

LIST_FIELDS = {"authors", "contributions", "keywords", "tags", "base_models"}
INT_FIELDS = {"year", "quality_score"}
TEXT_FIELDS = {
    "title",
    "title_zh",
    "abstract",
    "domain",
    "research_problem",
    "methodology",
    "venue",
    "filename",
}
EDITABLE_SECTIONS = LIST_FIELDS | INT_FIELDS | TEXT_FIELDS


class SectionUpdateRequest(BaseModel):
    content: str = ""


class RawUpdateRequest(BaseModel):
    raw: dict[str, Any] | str


def _parse_markdown_list(content: str) -> list[str]:
    items: list[str] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^[-*+]\s+", "", line)
        line = re.sub(r"^\d+\.\s+", "", line)
        line = line.strip()
        if line:
            items.append(line)
    return items


def _derive_tags(record: dict[str, Any]) -> list[str]:
    tags = record.get("tags")
    if isinstance(tags, list) and tags:
        return [str(t).strip() for t in tags if str(t).strip()]

    result: list[str] = []
    domain = str(record.get("domain") or "").strip()
    if domain:
        result.append(domain)
    for kw in record.get("keywords", []) or []:
        text = str(kw).strip()
        if text and text not in result:
            result.append(text)
        if len(result) >= 8:
            break
    return result


def _list_to_markdown(values: list[str]) -> str:
    if not values:
        return ""
    return "\n".join([f"- {item}" for item in values])


def _build_sections(record: dict[str, Any]) -> dict[str, str]:
    sections: dict[str, str] = {
        "title_zh": str(record.get("title_zh") or ""),
        "title": str(record.get("title") or ""),
        "abstract": str(record.get("abstract") or ""),
        "research_problem": str(record.get("research_problem") or ""),
        "methodology": str(record.get("methodology") or ""),
        "domain": str(record.get("domain") or ""),
        "venue": str(record.get("venue") or ""),
        "filename": str(record.get("filename") or ""),
        "year": "" if record.get("year") is None else str(record.get("year")),
        "quality_score": "" if record.get("quality_score") is None else str(record.get("quality_score")),
        "authors": _list_to_markdown(record.get("authors", []) or []),
        "contributions": _list_to_markdown(record.get("contributions", []) or []),
        "keywords": _list_to_markdown(record.get("keywords", []) or []),
        "tags": _list_to_markdown(record.get("tags", []) or []),
        "base_models": _list_to_markdown(record.get("base_models", []) or []),
    }
    sections["sql_raw"] = json.dumps(record, ensure_ascii=False, indent=2)
    return sections


def _detail_payload(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    normalized["task_id"] = normalized.get("id")
    normalized["tags"] = _derive_tags(normalized)
    return {
        "paper": normalized,
        "sections": _build_sections(normalized),
    }


@router.get("")
async def list_papers(
    q: str = Query(default="", max_length=200),
    tag: str = Query(default="", max_length=80),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    repo = await get_paper_repository()
    records = await repo.list_for_history(query=q.strip(), tag=tag.strip(), limit=limit, offset=offset)
    total = await repo.count()
    return {
        "records": [_detail_payload(r)["paper"] for r in records],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{task_id}")
async def get_paper(task_id: str):
    repo = await get_paper_repository()
    record = await repo.get_by_id(task_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"论文记录 {task_id} 不存在")
    return _detail_payload(record)


@router.patch("/{task_id}/sections/{section}")
async def update_section(task_id: str, section: str, req: SectionUpdateRequest):
    if section == "sql_raw":
        raise HTTPException(status_code=400, detail="sql_raw 请使用 /raw 接口更新")
    if section not in EDITABLE_SECTIONS:
        raise HTTPException(status_code=400, detail=f"不支持的 section: {section}")

    content = req.content or ""
    updates: dict[str, Any] = {}

    if section in LIST_FIELDS:
        updates[section] = _parse_markdown_list(content)
    elif section in INT_FIELDS:
        text = content.strip()
        if not text:
            updates[section] = None
        else:
            try:
                updates[section] = int(text)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"{section} 必须是数字") from exc
    else:
        updates[section] = content.strip()

    repo = await get_paper_repository()
    updated = await repo.update_partial(task_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail=f"论文记录 {task_id} 不存在")
    return _detail_payload(updated)


@router.patch("/{task_id}/raw")
async def update_raw(task_id: str, req: RawUpdateRequest):
    payload = req.raw
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"raw 不是合法 JSON: {e}") from e

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="raw 必须是对象")

    updates = {k: v for k, v in payload.items() if k in EDITABLE_SECTIONS}
    if not updates:
        raise HTTPException(status_code=400, detail="没有可更新字段")

    repo = await get_paper_repository()
    updated = await repo.update_partial(task_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail=f"论文记录 {task_id} 不存在")
    return _detail_payload(updated)
