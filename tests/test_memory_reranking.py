from __future__ import annotations

from datetime import UTC, datetime

from nexus.memory_lifecycle import normalize_memory
from nexus.rag import MemoryRetriever


NOW = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)


def memory(memory_id: str, text: str, **overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "id": memory_id,
        "text": text,
        "tags": ["nexus"],
        "created_at": "2026-01-01T00:00:00+00:00",
        "importance": 0.5,
        "importance_source": "user",
    }
    item.update(overrides)
    return normalize_memory(item, now=NOW)


def test_retrieval_filters_forgotten_expired_and_archived_by_default() -> None:
    retriever = MemoryRetriever()
    memories = [
        memory("active", "Nexus project architecture"),
        memory("forgotten", "Nexus project forgotten", status="forgotten"),
        memory("archived", "Nexus project archived", status="archived"),
        memory(
            "expired",
            "Nexus project expired",
            expires_at="2026-07-26T00:00:00+00:00",
        ),
    ]

    default = retriever.retrieve_result(memories, "Nexus project", now=NOW)
    with_archived = retriever.retrieve_result(
        memories,
        "Nexus project",
        include_archived=True,
        now=NOW,
    )

    assert [item["id"] for item in default.memories] == ["active"]
    assert {item["id"] for item in with_archived.memories} == {"active", "archived"}
    assert default.metadata["eligible_memories"] == 1
    assert default.metadata["include_archived"] is False


def test_retrieval_privacy_scope_never_returns_more_private_memory() -> None:
    retriever = MemoryRetriever()
    memories = [
        memory("private", "Nexus project private", privacy="private"),
        memory("personal", "Nexus project personal", privacy="personal"),
        memory("shared", "Nexus project shared", privacy="shared"),
    ]

    private_context = retriever.retrieve_result(
        memories, "Nexus project", privacy="private", now=NOW
    )
    shared_context = retriever.retrieve_result(
        memories, "Nexus project", privacy="shared", now=NOW
    )

    assert {item["id"] for item in private_context.memories} == {
        "private",
        "personal",
        "shared",
    }
    assert [item["id"] for item in shared_context.memories] == ["shared"]


def test_reranking_exposes_components_and_boosts_importance() -> None:
    retriever = MemoryRetriever()
    memories = [
        memory("low", "Nexus project plan", importance=0.1),
        memory("high", "Nexus project plan", importance=0.9),
    ]

    result = retriever.retrieve_result(memories, "Nexus project plan", now=NOW)

    assert [item["id"] for item in result.memories] == ["high", "low"]
    assert result.memories[0]["importance_score"] == 0.9
    assert result.memories[0]["rerank_score"] > result.memories[1]["rerank_score"]
    assert result.metadata["reranking"] == (
        "relevance_0.70+importance_0.15+recency_0.10+context_0.05"
    )


def test_reranking_uses_recency_and_task_context_tags() -> None:
    retriever = MemoryRetriever()
    memories = [
        memory(
            "old-research",
            "Nexus work note",
            tags=["research"],
            created_at="2025-01-01T00:00:00+00:00",
        ),
        memory(
            "new-study",
            "Nexus work note",
            tags=["study"],
            created_at="2026-07-26T00:00:00+00:00",
        ),
    ]

    normal = retriever.retrieve_result(memories, "Nexus work note", now=NOW)
    research = retriever.retrieve_result(
        memories,
        "Nexus work note",
        task_context="research experiment",
        now=NOW,
    )

    assert normal.memories[0]["id"] == "new-study"
    normal_old = next(item for item in normal.memories if item["id"] == "old-research")
    research_old = next(
        item for item in research.memories if item["id"] == "old-research"
    )
    assert research_old["context_score"] == 1.0
    assert research_old["rerank_score"] > normal_old["rerank_score"]


class StaleSemanticIndex:
    class Provider:
        provider_name = "fake"
        model_name = "fake-model"

    provider = Provider()

    def search(self, query: str, limit: int) -> list[dict[str, object]]:
        del query, limit
        return [
            {
                "id": "forgotten",
                "memory_id": "forgotten",
                "text": "Nexus stale vector",
                "tags": [],
                "created_at": "2026-01-01T00:00:00+00:00",
                "dense_score": 1.0,
            },
            {
                "id": "active",
                "memory_id": "active",
                "text": "Nexus active vector",
                "tags": [],
                "created_at": "2026-01-01T00:00:00+00:00",
                "dense_score": 0.8,
            },
        ]


def test_dense_stale_ids_are_rejected_before_fusion() -> None:
    retriever = MemoryRetriever(semantic_index=StaleSemanticIndex())  # type: ignore[arg-type]
    memories = [
        memory("active", "Nexus active vector"),
        memory("forgotten", "Nexus stale vector", status="forgotten"),
    ]

    result = retriever.retrieve_result(memories, "Nexus vector", now=NOW)

    assert [item["id"] for item in result.memories] == ["active"]
    assert result.metadata["dense_candidates"] == 1
