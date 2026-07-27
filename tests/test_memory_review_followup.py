from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.cli import memory_mutation_status
from nexus.memory_lifecycle import MemoryLifecycleError
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


def compressed_fixture(tmp_path: Path) -> tuple[NexusService, str, str]:
    nexus = service(tmp_path)
    first = nexus.add_memory(
        "Sensitive compressed source A",
        ["research"],
        importance=0.2,
        privacy="shared",
        now=OLD,
    )
    nexus.add_memory(
        "Sensitive compressed source B",
        ["research"],
        importance=0.2,
        privacy="shared",
        now=OLD,
    )
    result = nexus.compress_memories(
        older_than_days=90,
        max_importance=0.4,
        now=NOW,
    )
    return nexus, first.id, result["created"][0]


def test_purge_removes_derived_summaries_and_forgotten_source_blocks_restore(
    tmp_path: Path,
) -> None:
    nexus, source_id, summary_id = compressed_fixture(tmp_path)
    nexus.forget_memory(source_id, now=NOW)

    with pytest.raises(MemoryLifecycleError, match="source"):
        nexus.restore_memory(summary_id, now=NOW)

    nexus.purge_memory(source_id, confirm=True)

    with pytest.raises(MemoryLifecycleError, match="not found"):
        nexus.show_memory(summary_id)


def test_source_policy_update_tightens_derived_summary(tmp_path: Path) -> None:
    nexus, source_id, summary_id = compressed_fixture(tmp_path)

    nexus.update_memory(
        source_id,
        privacy="private",
        expires_at="2026-07-28T00:00:00+00:00",
        now=NOW,
    )
    summary = nexus.show_memory(summary_id)

    assert summary["privacy"] == "private"
    assert summary["expires_at"] == "2026-07-28T00:00:00+00:00"


class FailedAddIndexRetriever(MemoryRetriever):
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
            "error": "add index failed",
        }


def test_add_reports_partial_index_sync(tmp_path: Path) -> None:
    nexus = service(tmp_path, FailedAddIndexRetriever())

    memory = nexus.add_memory("New memory", [], now=NOW)

    assert memory.index_sync == {
        "enabled": True,
        "provider": "fake",
        "indexed": 0,
        "updated_at": "2026-07-27T08:00:00+00:00",
        "error": "add index failed",
    }
    assert memory_mutation_status(memory.__dict__) == "partial"
