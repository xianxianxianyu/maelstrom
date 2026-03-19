from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Author(BaseModel):
    name: str = Field(description="Author name")
    affiliation: str | None = Field(default=None, description="Author affiliation")


class ExternalIds(BaseModel):
    arxiv_id: str | None = Field(default=None, description="arXiv ID")
    s2_id: str | None = Field(default=None, description="Semantic Scholar ID")
    openreview_id: str | None = Field(default=None, description="OpenReview ID")
    openalex_id: str | None = Field(default=None, description="OpenAlex ID")
    doi: str | None = Field(default=None, description="DOI")
    corpus_id: str | None = Field(default=None, description="S2 Corpus ID")


class PaperRecord(BaseModel):
    paper_id: str = Field(description="Internal paper identifier")
    title: str = Field(description="Paper title")
    authors: list[Author] = Field(default_factory=list, description="Author list")
    abstract: str = Field(default="", description="Paper abstract")
    year: int | None = Field(default=None, description="Publication year")
    venue: str | None = Field(default=None, description="Publication venue")
    doi: str | None = Field(default=None, description="DOI")
    external_ids: ExternalIds = Field(default_factory=ExternalIds, description="External IDs")
    pdf_url: str | None = Field(default=None, description="PDF download URL")
    source: str = Field(description="Source adapter name")
    keywords: list[str] = Field(default_factory=list, description="Keywords")
    citation_count: int | None = Field(default=None, description="Citation count")
    retrieved_at: datetime = Field(description="Retrieval timestamp")
