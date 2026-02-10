"""术语管理 API 路由 — 领域术语表的 CRUD 和模糊搜索

提供以下端点：
- GET  /api/terminology/{domain}        获取领域术语表
- PUT  /api/terminology/{domain}/{term}  更新/创建术语
- DELETE /api/terminology/{domain}/{term} 删除术语
- GET  /api/terminology/search?q=xxx     模糊搜索术语

直接使用 GlossaryStore 进行持久化操作，无需经过 TerminologyAgent。

Requirements: 3.3, 3.5, 6.6
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from agent.tools.glossary_store import GlossaryStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/terminology", tags=["terminology"])

# 共享的 GlossaryStore 实例
_glossary_store = GlossaryStore()


# ── Pydantic 请求/响应模型 ──────────────────────────────────────


class TermUpdateRequest(BaseModel):
    """术语更新请求体"""

    chinese: str
    keep_english: bool = False


class TermEntry(BaseModel):
    """术语条目响应模型"""

    english: str
    chinese: str
    keep_english: bool
    domain: str
    source: str
    updated_at: str


# ── 端点实现 ────────────────────────────────────────────────────


@router.get("/search", response_model=list[TermEntry])
async def search_terms(q: str = Query(..., min_length=1, description="搜索关键词")):
    """模糊搜索术语（跨所有领域）

    在所有领域的术语表中搜索包含查询词的术语，
    匹配英文或中文字段（大小写不敏感）。

    Args:
        q: 搜索关键词

    Returns:
        匹配的术语条目列表
    """
    results = await _glossary_store.query(term=q, domain="")
    logger.info("🔍 术语搜索 '%s': 找到 %d 条", q, len(results))
    return [
        TermEntry(
            english=entry.english,
            chinese=entry.chinese,
            keep_english=entry.keep_english,
            domain=entry.domain,
            source=entry.source,
            updated_at=entry.updated_at,
        )
        for entry in results
    ]


@router.get("/{domain}", response_model=list[TermEntry])
async def get_domain_terms(domain: str):
    """获取指定领域的术语表

    加载并返回指定领域的所有术语条目。

    Args:
        domain: 领域名称（如 "nlp"、"cv"）

    Returns:
        该领域的术语条目列表
    """
    entries = await _glossary_store.load(domain)
    logger.info("📖 获取术语表 [%s]: %d 条", domain, len(entries))
    return [
        TermEntry(
            english=entry.english,
            chinese=entry.chinese,
            keep_english=entry.keep_english,
            domain=entry.domain,
            source=entry.source,
            updated_at=entry.updated_at,
        )
        for entry in entries
    ]


@router.put("/{domain}/{term}", response_model=TermEntry)
async def update_term(domain: str, term: str, body: TermUpdateRequest):
    """更新或创建术语

    如果术语已存在则更新其中文翻译和 keep_english 标志；
    如果不存在则新增条目。更新前会自动创建备份。

    Args:
        domain: 领域名称
        term: 英文术语
        body: 更新请求体，包含 chinese 和可选的 keep_english

    Returns:
        更新后的术语条目
    """
    await _glossary_store.update_entry(
        domain=domain,
        english=term,
        chinese=body.chinese,
        source="user_edit",
    )

    # 如果需要更新 keep_english，重新加载并修改
    if body.keep_english:
        entries = await _glossary_store.load(domain)
        for entry in entries:
            if entry.english.lower() == term.lower():
                entry.keep_english = body.keep_english
                break
        await _glossary_store.save(domain, entries)

    # 重新加载以获取最新状态
    entries = await _glossary_store.load(domain)
    for entry in entries:
        if entry.english.lower() == term.lower():
            logger.info("✏️ 术语更新 [%s]: %s → %s", domain, term, body.chinese)
            return TermEntry(
                english=entry.english,
                chinese=entry.chinese,
                keep_english=entry.keep_english,
                domain=entry.domain,
                source=entry.source,
                updated_at=entry.updated_at,
            )

    # 理论上不应到达这里，因为 update_entry 会创建条目
    raise HTTPException(status_code=500, detail="Failed to update term")


@router.delete("/{domain}/{term}")
async def delete_term(domain: str, term: str):
    """删除术语

    从指定领域的术语表中删除指定术语。如果术语不存在则返回 404。
    删除前会自动创建备份。

    Args:
        domain: 领域名称
        term: 英文术语

    Returns:
        删除确认消息
    """
    entries = await _glossary_store.load(domain)

    # 查找要删除的术语
    original_count = len(entries)
    entries = [e for e in entries if e.english.lower() != term.lower()]

    if len(entries) == original_count:
        raise HTTPException(
            status_code=404,
            detail=f"Term '{term}' not found in domain '{domain}'",
        )

    # 备份并保存
    await _glossary_store.backup(domain)
    await _glossary_store.save(domain, entries)

    logger.info("🗑️ 术语删除 [%s]: %s", domain, term)
    return {"message": f"Term '{term}' deleted from domain '{domain}'"}
