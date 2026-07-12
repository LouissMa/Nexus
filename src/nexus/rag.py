from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


class LocalMemoryEmbedder:
    """Small deterministic sparse embedder for local MVP memory retrieval."""

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


class MemoryRetriever:
    def __init__(self, embedder: LocalMemoryEmbedder | None = None):
        self.embedder = embedder or LocalMemoryEmbedder()

    def enrich_memory(self, memory: dict[str, Any]) -> dict[str, Any]:
        text = self._memory_text(memory)
        enriched = dict(memory)
        enriched["embedding"] = self.embedder.embed(text)
        return enriched

    def retrieve(self, memories: list[dict[str, Any]], query: str, limit: int = 5) -> list[dict[str, Any]]:
        query_embedding = self.embedder.embed(query)
        scored: list[tuple[float, dict[str, Any]]] = []

        for memory in memories:
            embedding = memory.get("embedding")
            if not isinstance(embedding, dict):
                embedding = self.embedder.embed(self._memory_text(memory))
            score = self.embedder.similarity(query_embedding, embedding)
            if score > 0:
                result = dict(memory)
                result["retrieval_score"] = round(score, 6)
                result.pop("embedding", None)
                scored.append((score, result))

        scored.sort(key=lambda item: (-item[0], item[1].get("created_at", "")), reverse=False)
        return [memory for _, memory in scored[:limit]]

    @staticmethod
    def _memory_text(memory: dict[str, Any]) -> str:
        tags = " ".join(memory.get("tags", []))
        return f"{memory.get('text', '')} {tags}".strip()
