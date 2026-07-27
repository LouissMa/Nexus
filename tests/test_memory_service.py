from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nexus.memory_lifecycle import MemoryLifecycleError
from nexus.rag import MemoryRetriever
from nexus.service import NexusService
from nexus.store import JsonStore


NOW = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)
OLD = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)


def service(tmp_path) -> NexusService:
    return NexusService(
        JsonStore(tmp_path / "state.json"), memory_retriever=MemoryRetriever()
    )


def test_add_memory_persists_lifecycle_metadata_and_merges_exact_duplicates(
    tmp_path,
) -> None:
    nexus = service(tmp_path)

    first = nexus.add_memory(
        "Prepare IELTS listening every day",
        ["ielts", "goal"],
        importance=0.8,
        privacy="personal",
        pinned=True,
        now=NOW,
    )
    duplicate = nexus.add_memory(
        " prepare IELTS listening every day! ",
        ["ielts"],
        now=NOW,
    )

    stored = nexus.list_memories(include_archived=True, include_forgotten=True)
    assert first.id == duplicate.id
    assert duplicate.duplicate_kind == "exact"
    assert len(stored) == 1
    assert stored[0]["importance"] == 0.8
    assert stored[0]["importance_source"] == "user"
    assert stored[0]["privacy"] == "personal"
    assert stored[0]["pinned"] is True
    assert stored[0]["duplicate_count"] == 1


def test_near_duplicate_is_stored_with_relation(tmp_path) -> None:
    nexus = service(tmp_path)
    first = nexus.add_memory("Prepare IELTS listening every day", ["ielts"], now=NOW)
    second = nexus.add_memory(
        "Prepare IELTS listening practice every day",
        ["ielts"],
        now=NOW,
    )

    assert second.id != first.id
    assert second.duplicate_kind == "near"
    assert nexus.show_memory(second.id)["duplicate_of"] == first.id


def test_update_and_relations_preserve_history(tmp_path) -> None:
    nexus = service(tmp_path)
    old = nexus.add_memory("My IELTS test is in September", ["exam"], now=NOW)
    new = nexus.add_memory("My IELTS test is in October", ["exam"], now=NOW)

    updated = nexus.update_memory(
        new.id,
        importance=0.95,
        privacy="shared",
        expires_at="2027-01-01T00:00:00+00:00",
        pinned=True,
        now=NOW,
    )
    relation = nexus.relate_memory(new.id, "supersedes", old.id, now=NOW)
    conflict = nexus.relate_memory(new.id, "conflicts_with", old.id, now=NOW)

    assert updated["importance"] == 0.95
    assert updated["importance_source"] == "user"
    assert relation["memory"]["supersedes"] == old.id
    assert relation["target"]["status"] == "archived"
    assert conflict["memory"]["conflicts_with"] == [old.id]
    assert nexus.show_memory(old.id)["conflicts_with"] == [new.id]


def test_archive_forget_restore_and_confirmed_purge(tmp_path) -> None:
    nexus = service(tmp_path)
    item = nexus.add_memory("A private old note", [], now=NOW)

    assert nexus.archive_memory(item.id, now=NOW)["status"] == "archived"
    assert nexus.restore_memory(item.id, now=NOW)["status"] == "active"
    assert nexus.forget_memory(item.id, now=NOW)["status"] == "forgotten"
    with pytest.raises(MemoryLifecycleError, match="confirmation"):
        nexus.purge_memory(item.id, confirm=False)
    assert nexus.restore_memory(item.id, now=NOW)["status"] == "active"
    with pytest.raises(MemoryLifecycleError, match="forgotten"):
        nexus.purge_memory(item.id, confirm=True)
    nexus.forget_memory(item.id, now=NOW)
    assert nexus.purge_memory(item.id, confirm=True)["purged"] is True
    with pytest.raises(MemoryLifecycleError, match="not found"):
        nexus.show_memory(item.id)


def test_compression_dry_run_and_apply_are_inspectable_and_idempotent(tmp_path) -> None:
    nexus = service(tmp_path)
    first = nexus.add_memory("Read paper A", ["research"], importance=0.2, now=OLD)
    second = nexus.add_memory("Read paper B", ["research"], importance=0.3, now=OLD)

    preview = nexus.compress_memories(
        older_than_days=90,
        max_importance=0.4,
        dry_run=True,
        now=NOW,
    )
    applied = nexus.compress_memories(
        older_than_days=90,
        max_importance=0.4,
        dry_run=False,
        now=NOW,
    )
    repeated = nexus.compress_memories(
        older_than_days=90,
        max_importance=0.4,
        dry_run=False,
        now=NOW,
    )

    assert set(preview["groups"][0]["source_ids"]) == {first.id, second.id}
    assert preview["created"] == []
    assert len(applied["created"]) == 1
    summary = nexus.show_memory(applied["created"][0])
    assert set(summary["summary_of"]) == {first.id, second.id}
    assert nexus.show_memory(first.id)["status"] == "archived"
    assert repeated["groups"] == []


def test_maintenance_archives_only_expired_unpinned_active_memories(tmp_path) -> None:
    nexus = service(tmp_path)
    expired = nexus.add_memory(
        "Temporary reminder",
        [],
        expires_at="2026-07-26T00:00:00+00:00",
        now=NOW,
    )
    pinned = nexus.add_memory(
        "Pinned reminder",
        [],
        expires_at="2026-07-26T00:00:00+00:00",
        pinned=True,
        now=NOW,
    )

    preview = nexus.maintain_memories(now=NOW, dry_run=True)
    applied = nexus.maintain_memories(now=NOW, dry_run=False)

    assert preview["expired_ids"] == [expired.id]
    assert nexus.show_memory(expired.id)["status"] == "archived"
    assert nexus.show_memory(pinned.id)["status"] == "active"
    assert applied["archived_ids"] == [expired.id]


def test_legacy_state_is_normalized_without_requiring_migration(tmp_path) -> None:
    store = JsonStore(tmp_path / "state.json")
    store.save(
        {
            "memories": [
                {
                    "id": "legacy",
                    "text": "Legacy memory",
                    "tags": [],
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "embedding": {"legacy": 1.0},
                }
            ],
            "goals": [],
            "daily_tasks": [],
            "rag_index": None,
        }
    )
    nexus = NexusService(store)

    item = nexus.show_memory("legacy")

    assert item["status"] == "active"
    assert item["privacy"] == "private"
    assert "embedding" not in item
