from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.cli import memory_mutation_status
from nexus.memory_lifecycle import MemoryLifecycleError, normalize_memory
from nexus.rag import MemoryRetriever
from nexus.service import NexusService
from nexus.store import JsonStore


NOW = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)
OLD = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)


def service(tmp_path: Path, retriever: MemoryRetriever | None = None) -> NexusService:
    return NexusService(
        JsonStore(tmp_path / "state.json"),
        memory_retriever=retriever or MemoryRetriever(),
    )


def test_forgetting_compressed_source_also_forgets_derived_summary(
    tmp_path: Path,
) -> None:
    nexus = service(tmp_path)
    first = nexus.add_memory("Sensitive note A", ["private"], importance=0.2, now=OLD)
    nexus.add_memory("Sensitive note B", ["private"], importance=0.2, now=OLD)
    compressed = nexus.compress_memories(
        older_than_days=90,
        max_importance=0.4,
        now=NOW,
    )
    summary_id = compressed["created"][0]

    nexus.forget_memory(first.id, now=NOW)

    assert nexus.show_memory(summary_id)["status"] == "forgotten"
    retrieved = nexus.retrieve_memories_result(
        "Sensitive note",
        include_archived=True,
        now=NOW,
    )
    assert summary_id not in {item["id"] for item in retrieved["results"]}


def test_compression_separates_privacy_scopes_and_copies_earliest_expiry(
    tmp_path: Path,
) -> None:
    nexus = service(tmp_path)
    for privacy in ("private", "shared"):
        nexus.add_memory(
            f"{privacy} note A",
            ["research"],
            importance=0.2,
            privacy=privacy,
            expires_at="2026-08-01T00:00:00+00:00",
            now=OLD,
        )
        nexus.add_memory(
            f"{privacy} note B",
            ["research"],
            importance=0.2,
            privacy=privacy,
            expires_at="2026-09-01T00:00:00+00:00",
            now=OLD,
        )

    compressed = nexus.compress_memories(
        older_than_days=90,
        max_importance=0.4,
        now=NOW,
    )
    summaries = [nexus.show_memory(memory_id) for memory_id in compressed["created"]]

    assert {item["privacy"] for item in summaries} == {"private", "shared"}
    assert all(item["expires_at"] == "2026-08-01T00:00:00+00:00" for item in summaries)


def test_forgotten_memory_cannot_be_archived_or_superseded(tmp_path: Path) -> None:
    nexus = service(tmp_path)
    forgotten = nexus.add_memory("Forgotten fact", [], now=NOW)
    replacement = nexus.add_memory("Replacement fact", [], now=NOW)
    nexus.forget_memory(forgotten.id, now=NOW)

    with pytest.raises(MemoryLifecycleError, match="forgotten"):
        nexus.archive_memory(forgotten.id, now=NOW)
    with pytest.raises(MemoryLifecycleError, match="forgotten"):
        nexus.relate_memory(
            replacement.id,
            "supersedes",
            forgotten.id,
            now=NOW,
        )


def test_reranking_happens_before_final_limit() -> None:
    retriever = MemoryRetriever()
    memories = [
        normalize_memory(
            {
                "id": "exact-low",
                "text": "alpha beta",
                "tags": [],
                "created_at": "2010-01-01T00:00:00+00:00",
                "importance": 0.0,
            },
            now=NOW,
        ),
        normalize_memory(
            {
                "id": "context-high",
                "text": "alpha beta",
                "tags": [],
                "created_at": "2026-07-27T00:00:00+00:00",
                "importance": 1.0,
                "pinned": True,
            },
            now=NOW,
        ),
    ]

    result = retriever.retrieve_result(
        memories,
        "alpha beta",
        limit=1,
        task_context="research",
        now=NOW,
    )

    assert result.memories[0]["id"] == "context-high"


def test_list_and_search_exclude_expired_memory(tmp_path: Path) -> None:
    nexus = service(tmp_path)
    expired = nexus.add_memory(
        "Expired research secret",
        ["research"],
        expires_at="2026-07-26T00:00:00+00:00",
        now=NOW,
    )

    assert expired.id not in {item["id"] for item in nexus.list_memories(now=NOW)}
    assert nexus.search_memories("research", now=NOW) == []


class FailedIndexRetriever(MemoryRetriever):
    def index_memories(
        self,
        memories: list[dict],
        recreate: bool = False,
    ) -> dict:
        del memories, recreate
        return {
            "enabled": True,
            "provider": "fake",
            "indexed": 0,
            "error": "vector backend unavailable",
        }


def test_mutation_reports_partial_when_vector_refresh_fails(tmp_path: Path) -> None:
    nexus = service(tmp_path, FailedIndexRetriever())
    item = nexus.add_memory("Remember this", [], now=NOW)

    result = nexus.forget_memory(item.id, now=NOW)

    assert result["index_sync"]["error"] == "vector backend unavailable"
    assert memory_mutation_status(result) == "partial"
