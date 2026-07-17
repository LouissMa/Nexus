from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import EmbeddingSettings
from .embeddings import (
    EmbeddingError,
    EmbeddingProvider,
    FastEmbedProvider,
    OpenAICompatibleEmbeddingProvider,
)
from .vector_store import QdrantVectorStore, VectorStoreError

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


@dataclass(frozen=True)
class RetrievalResult:
    memories: list[dict[str, Any]]
    metadata: dict[str, Any]


class LocalMemoryEmbedder:
    """Deterministic sparse embedder kept as lexical/offline retrieval."""

    def embed(self, text: str) -> dict[str, float]:
        tokens = self._tokens(text)
        if not tokens:
            return {}
        counts = Counter(tokens)
        norm = math.sqrt(sum(count * count for count in counts.values()))
        if norm == 0:
            return {}
        return {token: count / norm for token, count in counts.items()}

    def similarity(self, left: dict[str, float], right: dict[str, float]) -> float:
        if not left or not right:
            return 0.0
        if len(left) > len(right):
            left, right = right, left
        return sum(weight * right.get(token, 0.0) for token, weight in left.items())

    def _tokens(self, text: str) -> list[str]:
        raw_tokens = [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]
        tokens: list[str] = []
        latin_terms: list[str] = []
        chinese_chars: list[str] = []
        for token in raw_tokens:
            if len(token) == 1 and "\u4e00" <= token <= "\u9fff":
                chinese_chars.append(token)
                tokens.append(token)
            else:
                latin_terms.append(token)
                tokens.append(token)
        for term in latin_terms:
            tokens.extend(self._latin_ngrams(term))
        for index in range(len(chinese_chars) - 1):
            tokens.append(chinese_chars[index] + chinese_chars[index + 1])
        return tokens

    @staticmethod
    def _latin_ngrams(term: str) -> list[str]:
        if len(term) <= 3:
            return []
        return [term[index:index + 3] for index in range(len(term) - 2)]


class SemanticMemoryIndex:
    def __init__(self, provider: EmbeddingProvider, vector_store: QdrantVectorStore):
        self.provider = provider
        self.vector_store = vector_store

    def index(self, memories: list[dict[str, Any]], recreate: bool = False) -> dict[str, Any]:
        if recreate and not memories:
            self.vector_store.clear()
            vectors: list[list[float]] = []
        else:
            texts = [MemoryRetriever.memory_text(memory) for memory in memories]
            vectors = self.provider.embed_documents(texts)
        indexed = self.vector_store.upsert(memories, vectors, recreate=recreate)
        dimension = len(vectors[0]) if vectors else 0
        return {
            "enabled": True,
            "provider": self.provider.provider_name,
            "model": self.provider.model_name,
            "collection": self.vector_store.collection_name,
            "dimension": dimension,
            "indexed": indexed,
            "error": None,
        }

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        vector = self.provider.embed_query(query)
        return self.vector_store.search(vector, limit)

    def status(self) -> dict[str, Any]:
        status = self.vector_store.status()
        status.update(
            {
                "enabled": True,
                "provider": self.provider.provider_name,
                "model": self.provider.model_name,
                "collection": self.vector_store.collection_name,
                "error": None,
            }
        )
        return status


class MemoryRetriever:
    def __init__(
        self,
        embedder: LocalMemoryEmbedder | None = None,
        semantic_index: SemanticMemoryIndex | None = None,
        configuration_error: str | None = None,
    ):
        self.embedder = embedder or LocalMemoryEmbedder()
        self.semantic_index = semantic_index
        self.configuration_error = configuration_error

    def enrich_memory(self, memory: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(memory)
        enriched["embedding"] = self.embedder.embed(self.memory_text(memory))
        return enriched

    def index_memories(
        self,
        memories: list[dict[str, Any]],
        recreate: bool = False,
    ) -> dict[str, Any] | None:
        if self.semantic_index is None:
            if self.configuration_error:
                return self._error_report(self.configuration_error)
            return None
        try:
            return self.semantic_index.index(memories, recreate=recreate)
        except (EmbeddingError, VectorStoreError) as exc:
            return self._error_report(str(exc))

    def reindex(self, memories: list[dict[str, Any]]) -> dict[str, Any]:
        if self.semantic_index is None:
            message = self.configuration_error or (
                "Semantic RAG is disabled. Configure FastEmbed or an embedding API first."
            )
            return self._error_report(message)
        return self.index_memories(memories, recreate=True) or self._error_report(
            "Semantic index is unavailable."
        )

    def status(self) -> dict[str, Any]:
        if self.semantic_index is None:
            return {
                "enabled": False,
                "strategy": "local_sparse_embedding",
                "error": self.configuration_error,
            }
        try:
            return self.semantic_index.status()
        except VectorStoreError as exc:
            return self._error_report(str(exc))

    def retrieve(self, memories: list[dict[str, Any]], query: str, limit: int = 5) -> list[dict[str, Any]]:
        return self.retrieve_result(memories, query, limit).memories

    def retrieve_result(
        self,
        memories: list[dict[str, Any]],
        query: str,
        limit: int = 5,
    ) -> RetrievalResult:
        candidate_limit = max(limit * 4, limit)
        sparse = self._sparse_retrieve(memories, query, candidate_limit)
        dense: list[dict[str, Any]] = []
        dense_error: str | None = self.configuration_error

        if self.semantic_index is not None:
            try:
                dense = self.semantic_index.search(query, candidate_limit)
                dense_error = None
            except (EmbeddingError, VectorStoreError) as exc:
                dense_error = str(exc)

        if dense:
            results = self._fuse(dense, sparse, limit)
            strategy = "hybrid_dense_sparse"
        else:
            results = []
            for memory in sparse[:limit]:
                result = dict(memory)
                result["retrieval_score"] = result.pop("sparse_score")
                result["dense_score"] = None
                results.append(result)
            strategy = "local_sparse_embedding"

        metadata = {
            "query": query,
            "strategy": strategy,
            "limit": limit,
            "dense_candidates": len(dense),
            "sparse_candidates": len(sparse),
            "provider": (
                self.semantic_index.provider.provider_name if self.semantic_index else None
            ),
            "model": self.semantic_index.provider.model_name if self.semantic_index else None,
            "error": dense_error,
        }
        return RetrievalResult(results, metadata)

    def _sparse_retrieve(
        self,
        memories: list[dict[str, Any]],
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        query_embedding = self.embedder.embed(query)
        scored: list[tuple[float, dict[str, Any]]] = []
        for memory in memories:
            embedding = memory.get("embedding")
            if not isinstance(embedding, dict):
                embedding = self.embedder.embed(self.memory_text(memory))
            score = self.embedder.similarity(query_embedding, embedding)
            if score > 0:
                result = self._public_memory(memory)
                result["sparse_score"] = round(score, 6)
                scored.append((score, result))
        scored.sort(key=lambda item: (-item[0], item[1].get("created_at", "")))
        return [memory for _, memory in scored[:limit]]

    def _fuse(
        self,
        dense: list[dict[str, Any]],
        sparse: list[dict[str, Any]],
        limit: int,
    ) -> list[dict[str, Any]]:
        candidates: dict[str, dict[str, Any]] = {}
        for memory in dense:
            memory_id = str(memory.get("memory_id") or memory.get("id"))
            result = self._public_memory(memory)
            result["id"] = memory.get("id") or memory_id
            result["dense_score"] = max(0.0, float(memory.get("dense_score", 0.0)))
            result["sparse_score"] = 0.0
            candidates[memory_id] = result
        for memory in sparse:
            memory_id = str(memory.get("id"))
            result = candidates.setdefault(memory_id, self._public_memory(memory))
            result.setdefault("dense_score", 0.0)
            result["sparse_score"] = float(memory.get("sparse_score", 0.0))

        fused: list[dict[str, Any]] = []
        for memory in candidates.values():
            dense_score = float(memory.get("dense_score", 0.0))
            sparse_score = float(memory.get("sparse_score", 0.0))
            if dense_score and sparse_score:
                score = 0.8 * dense_score + 0.2 * sparse_score
            elif dense_score:
                score = dense_score
            else:
                score = 0.9 * sparse_score
            memory["retrieval_score"] = round(score, 6)
            memory["dense_score"] = round(dense_score, 6) if dense_score else None
            memory["sparse_score"] = round(sparse_score, 6) if sparse_score else None
            memory.pop("memory_id", None)
            fused.append(memory)
        fused.sort(key=lambda item: (-item["retrieval_score"], item.get("created_at", "")))
        return fused[:limit]

    @staticmethod
    def memory_text(memory: dict[str, Any]) -> str:
        tags = " ".join(memory.get("tags", []))
        return f"{memory.get('text', '')} {tags}".strip()

    @staticmethod
    def _public_memory(memory: dict[str, Any]) -> dict[str, Any]:
        result = dict(memory)
        result.pop("embedding", None)
        return result

    def _error_report(self, message: str) -> dict[str, Any]:
        return {
            "enabled": self.semantic_index is not None,
            "provider": (
                self.semantic_index.provider.provider_name if self.semantic_index else None
            ),
            "model": self.semantic_index.provider.model_name if self.semantic_index else None,
            "indexed": 0,
            "error": message,
        }


def build_memory_retriever(settings: EmbeddingSettings, home: Path) -> MemoryRetriever:
    if not settings.semantic_enabled:
        return MemoryRetriever()
    if not settings.is_configured:
        return MemoryRetriever(configuration_error="Embedding provider is not fully configured.")

    if settings.provider == "fastembed":
        provider: EmbeddingProvider = FastEmbedProvider(settings.model, cache_dir=home / "models")
    else:
        provider = OpenAICompatibleEmbeddingProvider(
            model_name=settings.model,
            api_key=settings.api_key or "",
            base_url=settings.base_url or "",
            timeout_seconds=settings.timeout_seconds,
        )
    vector_store = QdrantVectorStore(
        collection_name=settings.collection_name,
        path=home / "qdrant",
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        timeout_seconds=settings.timeout_seconds,
    )
    return MemoryRetriever(semantic_index=SemanticMemoryIndex(provider, vector_store))
