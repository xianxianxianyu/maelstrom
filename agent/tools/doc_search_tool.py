"""DocSearchTool 和 VectorIndex — 文档向量检索工具

DocSearchTool 封装 VectorIndex 的检索操作，供 Agent 调用。
VectorIndex 基于 numpy 的余弦相似度实现简单的内存向量检索。

功能：
- 文档分块（按段落，~500 字符）
- 基于 hash 的确定性 embedding（MVP 方案，可替换为 LLM embedding）
- 余弦相似度检索
- 按 doc_id 隔离检索范围

DocSearchTool 支持的 action：
- "search": 检索相关文档片段，需要 query (str)，可选 doc_id (str)、top_k (int)
- "index": 索引文档，需要 doc_id (str)、markdown (str)、doc_name (str)
- "clear": 清除索引，可选 doc_id (str)

Requirements: 4.1, 4.2, 5.3
"""

import hashlib
import logging
from typing import Any

import numpy as np
from numpy import ndarray

from agent.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# Exceptions considered recoverable (IO/transient issues)
_RECOVERABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
)

# Supported action names
_VALID_ACTIONS = frozenset({"search", "index", "clear"})

# Default embedding dimension for hash-based embeddings
_EMBEDDING_DIM = 128

# Target chunk size in characters
_TARGET_CHUNK_SIZE = 500


class VectorIndex:
    """基于 numpy 的简单向量检索

    使用内存存储文档分块及其 embedding，通过余弦相似度进行检索。
    MVP 阶段使用 hash-based 确定性 embedding，可通过覆写 _get_embedding
    方法替换为真实的 LLM embedding。
    """

    def __init__(self) -> None:
        self._chunks: list[dict] = []  # {"text": str, "source": str, "doc_id": str, "embedding": ndarray}

    async def index_document(self, doc_id: str, markdown: str, doc_name: str) -> int:
        """将文档按段落分块并建立索引

        Args:
            doc_id: 文档唯一标识
            markdown: 文档的 Markdown 内容
            doc_name: 文档显示名称（用于引用来源）

        Returns:
            int: 索引的分块数量
        """
        chunks = self._split_into_chunks(markdown)
        count = 0
        for chunk in chunks:
            embedding = await self._get_embedding(chunk)
            self._chunks.append({
                "text": chunk,
                "source": doc_name,
                "doc_id": doc_id,
                "embedding": embedding,
            })
            count += 1

        logger.info(
            "Indexed document '%s' (doc_id=%s): %d chunks",
            doc_name, doc_id, count,
        )
        return count

    async def search(
        self, query: str, doc_id: str | None = None, top_k: int = 5
    ) -> list[dict]:
        """余弦相似度检索

        Args:
            query: 查询文本
            doc_id: 可选，限制检索范围到指定文档
            top_k: 返回最相关的 top_k 个结果

        Returns:
            list[dict]: 检索结果列表，每项包含 text、source、score
        """
        query_emb = await self._get_embedding(query)

        candidates = self._chunks
        if doc_id is not None:
            candidates = [c for c in candidates if c["doc_id"] == doc_id]

        if not candidates:
            return []

        scores = [self._cosine_sim(query_emb, c["embedding"]) for c in candidates]
        top_indices = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )[:top_k]

        return [
            {
                "text": candidates[i]["text"],
                "source": candidates[i]["source"],
                "score": scores[i],
            }
            for i in top_indices
        ]

    def clear(self, doc_id: str | None = None) -> int:
        """清除索引

        Args:
            doc_id: 可选，仅清除指定文档的分块。如果为 None，清除所有分块。

        Returns:
            int: 被清除的分块数量
        """
        if doc_id is None:
            count = len(self._chunks)
            self._chunks.clear()
            logger.info("Cleared all %d chunks from index", count)
            return count

        original_count = len(self._chunks)
        self._chunks = [c for c in self._chunks if c["doc_id"] != doc_id]
        removed = original_count - len(self._chunks)
        logger.info("Cleared %d chunks for doc_id=%s", removed, doc_id)
        return removed

    @property
    def chunk_count(self) -> int:
        """当前索引中的分块总数"""
        return len(self._chunks)

    def _split_into_chunks(self, markdown: str) -> list[str]:
        """将 Markdown 文本按段落分块，合并小段落到 ~500 字符

        分块策略：
        1. 按双换行符分割为段落
        2. 过滤空段落
        3. 合并相邻的小段落，使每个分块接近 _TARGET_CHUNK_SIZE 字符

        Args:
            markdown: Markdown 文本

        Returns:
            list[str]: 分块列表
        """
        if not markdown or not markdown.strip():
            return []

        # Split by double newlines (paragraph boundaries)
        paragraphs = markdown.split("\n\n")
        # Strip and filter empty paragraphs
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        if not paragraphs:
            return []

        # Merge small paragraphs to approach target chunk size
        chunks: list[str] = []
        current_chunk = paragraphs[0]

        for para in paragraphs[1:]:
            # If adding this paragraph keeps us under the target, merge
            if len(current_chunk) + len(para) + 2 <= _TARGET_CHUNK_SIZE:
                current_chunk = current_chunk + "\n\n" + para
            else:
                chunks.append(current_chunk)
                current_chunk = para

        # Don't forget the last chunk
        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    async def _get_embedding(self, text: str) -> ndarray:
        """获取文本的 embedding 向量

        MVP 实现：使用 hashlib 生成确定性的 128 维向量。
        同一文本始终产生相同的 embedding，便于测试。
        此方法为 async 且可覆写，以便后续替换为真实的 LLM embedding。

        Args:
            text: 输入文本

        Returns:
            ndarray: 128 维 float64 向量（已归一化）
        """
        # Use SHA-512 to get 64 bytes, then extend to fill 128 floats
        h = hashlib.sha512(text.encode("utf-8")).digest()
        # Convert bytes to float array: each byte -> float in [-1, 1]
        raw = np.array([((b / 255.0) * 2 - 1) for b in h], dtype=np.float64)
        # Extend to _EMBEDDING_DIM by repeating
        if len(raw) < _EMBEDDING_DIM:
            repeats = (_EMBEDDING_DIM // len(raw)) + 1
            raw = np.tile(raw, repeats)[:_EMBEDDING_DIM]
        else:
            raw = raw[:_EMBEDDING_DIM]
        # Normalize to unit vector
        norm = np.linalg.norm(raw)
        if norm > 0:
            raw = raw / norm
        return raw

    @staticmethod
    def _cosine_sim(a: ndarray, b: ndarray) -> float:
        """计算两个向量的余弦相似度

        Args:
            a: 向量 a
            b: 向量 b

        Returns:
            float: 余弦相似度值，范围 [-1, 1]
        """
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


class DocSearchTool(BaseTool):
    """文档检索工具 — 封装 VectorIndex 的索引和检索操作

    支持的 action：
    - "search": 检索相关文档片段
    - "index": 索引新文档
    - "clear": 清除索引
    """

    def __init__(self, vector_index: VectorIndex | None = None) -> None:
        """初始化 DocSearchTool

        Args:
            vector_index: 可选的 VectorIndex 实例（用于依赖注入/测试）。
                         如果未提供，则创建默认的 VectorIndex。
        """
        self._index = vector_index or VectorIndex()

    @property
    def name(self) -> str:
        return "doc_search"

    @property
    def description(self) -> str:
        return "文档向量检索工具，支持文档索引、相似度检索和索引清除"

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行文档检索操作

        Args:
            action (str): 操作类型，必需。取值：
                - "search": 检索文档片段，需要 query (str)，可选 doc_id (str)、top_k (int, 默认 5)
                - "index": 索引文档，需要 doc_id (str)、markdown (str)、doc_name (str)
                - "clear": 清除索引，可选 doc_id (str)
            **kwargs: 操作相关的参数

        Returns:
            ToolResult: 执行结果
        """
        action: str | None = kwargs.get("action")

        # --- Validate action ---
        if action is None:
            return ToolResult(
                success=False,
                error="Missing required argument: action",
                recoverable=False,
            )

        if not isinstance(action, str):
            return ToolResult(
                success=False,
                error=f"action must be str, got {type(action).__name__}",
                recoverable=False,
            )

        if action not in _VALID_ACTIONS:
            return ToolResult(
                success=False,
                error=f"Unknown action: {action}",
                recoverable=False,
            )

        # --- Dispatch to action handler ---
        try:
            if action == "search":
                return await self._handle_search(**kwargs)
            elif action == "index":
                return await self._handle_index(**kwargs)
            elif action == "clear":
                return await self._handle_clear(**kwargs)
        except _RECOVERABLE_EXCEPTIONS as e:
            logger.warning("DocSearch tool recoverable error: %s", e)
            return ToolResult(
                success=False,
                error=str(e),
                recoverable=True,
            )
        except Exception as e:
            logger.error("DocSearch tool non-recoverable error: %s", e)
            return ToolResult(
                success=False,
                error=str(e),
                recoverable=False,
            )

        # Should not reach here
        return ToolResult(
            success=False,
            error=f"Unknown action: {action}",
            recoverable=False,
        )

    async def _handle_search(self, **kwargs: Any) -> ToolResult:
        """处理 search 操作：检索相关文档片段"""
        query: str | None = kwargs.get("query")
        doc_id: str | None = kwargs.get("doc_id")
        top_k: int = kwargs.get("top_k", 5)

        if query is None:
            return ToolResult(
                success=False,
                error="Missing required argument for search: query",
                recoverable=False,
            )

        if not isinstance(query, str):
            return ToolResult(
                success=False,
                error=f"query must be str, got {type(query).__name__}",
                recoverable=False,
            )

        if not isinstance(top_k, int):
            return ToolResult(
                success=False,
                error=f"top_k must be int, got {type(top_k).__name__}",
                recoverable=False,
            )

        chunks = await self._index.search(query, doc_id=doc_id, top_k=top_k)

        logger.info(
            "DocSearch query '%s' (doc_id=%s, top_k=%d): %d results",
            query[:50], doc_id or "all", top_k, len(chunks),
        )

        return ToolResult(
            success=True,
            data={"chunks": chunks},
        )

    async def _handle_index(self, **kwargs: Any) -> ToolResult:
        """处理 index 操作：索引新文档"""
        doc_id: str | None = kwargs.get("doc_id")
        markdown: str | None = kwargs.get("markdown")
        doc_name: str | None = kwargs.get("doc_name")

        # Validate required arguments
        missing = []
        if doc_id is None:
            missing.append("doc_id")
        if markdown is None:
            missing.append("markdown")
        if doc_name is None:
            missing.append("doc_name")

        if missing:
            return ToolResult(
                success=False,
                error=f"Missing required argument(s) for index: {', '.join(missing)}",
                recoverable=False,
            )

        if not isinstance(doc_id, str):
            return ToolResult(
                success=False,
                error=f"doc_id must be str, got {type(doc_id).__name__}",
                recoverable=False,
            )

        if not isinstance(markdown, str):
            return ToolResult(
                success=False,
                error=f"markdown must be str, got {type(markdown).__name__}",
                recoverable=False,
            )

        if not isinstance(doc_name, str):
            return ToolResult(
                success=False,
                error=f"doc_name must be str, got {type(doc_name).__name__}",
                recoverable=False,
            )

        chunk_count = await self._index.index_document(doc_id, markdown, doc_name)

        logger.info(
            "DocSearch indexed document '%s' (doc_id=%s): %d chunks",
            doc_name, doc_id, chunk_count,
        )

        return ToolResult(
            success=True,
            data={"indexed_chunks": chunk_count, "doc_id": doc_id},
        )

    async def _handle_clear(self, **kwargs: Any) -> ToolResult:
        """处理 clear 操作：清除索引"""
        doc_id: str | None = kwargs.get("doc_id")

        removed = self._index.clear(doc_id=doc_id)

        logger.info(
            "DocSearch cleared index (doc_id=%s): %d chunks removed",
            doc_id or "all", removed,
        )

        return ToolResult(
            success=True,
            data={"removed_chunks": removed},
        )
