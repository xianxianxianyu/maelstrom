"""Abstract base class for paper search adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from maelstrom.schemas.paper import PaperRecord


@dataclass
class RawPaperResult:
    """Intermediate data structure returned by adapter search before normalization."""
    source: str
    raw_id: str
    title: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    pdf_url: str | None = None
    published_date: str | None = None
    citation_count: int | None = None
    external_ids: dict[str, str | None] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


class BaseAdapter(ABC):
    """Abstract base for all paper retrieval adapters."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique name identifying this source (e.g. 'arxiv', 's2')."""

    @abstractmethod
    async def search(self, query: str, max_results: int = 20) -> list[RawPaperResult]:
        """Search for papers. Returns raw results."""

    @abstractmethod
    def normalize(self, raw: RawPaperResult) -> PaperRecord:
        """Convert a RawPaperResult into a canonical PaperRecord."""
