from maelstrom.adapters.base import BaseAdapter, RawPaperResult
from maelstrom.adapters.arxiv_adapter import ArxivAdapter
from maelstrom.adapters.s2_adapter import SemanticScholarAdapter
from maelstrom.adapters.openalex_adapter import OpenAlexAdapter
from maelstrom.adapters.openreview_adapter import OpenReviewAdapter

__all__ = [
    "BaseAdapter", "RawPaperResult",
    "ArxivAdapter", "SemanticScholarAdapter", "OpenAlexAdapter", "OpenReviewAdapter",
]
