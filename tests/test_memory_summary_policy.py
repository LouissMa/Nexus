from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.memory_lifecycle import MemoryLifecycleError
from nexus.service import NexusService
from nexus.store import JsonStore


NOW = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)
OLD = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)


def compressed_fixture(tmp_path: Path) -> tuple[NexusService, Path, str]:
    store = JsonStore(tmp_path / "state.json")
    nexus = NexusService(store)
    for suffix, expiry in (
        ("A", "2026-08-01T00:00:00+00:00"),
        ("B", "2026-09-01T00:00:00+00:00"),
    ):
        nexus.add_memory(
            f"Private source {suffix}",
            ["research"],
            importance=0.2,
            privacy="private",
            expires_at=expiry,
            now=OLD,
        )
    compressed = nexus.compress_memories(
        older_than_days=90,
        max_importance=0.4,
        now=NOW,
    )
    return nexus, store.path, compressed["created"][0]


def test_derived_summary_policy_cannot_be_overridden_directly(tmp_path: Path) -> None:
    nexus, _, summary_id = compressed_fixture(tmp_path)

    with pytest.raises(MemoryLifecycleError, match="controlled by its sources"):
        nexus.update_memory(summary_id, privacy="shared", now=NOW)
    with pytest.raises(MemoryLifecycleError, match="controlled by its sources"):
        nexus.update_memory(summary_id, expires_at=None, now=NOW)
    with pytest.raises(MemoryLifecycleError, match="controlled by its sources"):
        nexus.update_memory(summary_id, pinned=True, now=NOW)


def test_restore_recomputes_derived_summary_policy(tmp_path: Path) -> None:
    nexus, state_path, summary_id = compressed_fixture(tmp_path)
    nexus.forget_memory(summary_id, now=NOW)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    summary = next(item for item in state["memories"] if item["id"] == summary_id)
    summary["privacy"] = "shared"
    summary["expires_at"] = None
    summary["pinned"] = True
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    restored = nexus.restore_memory(summary_id, now=NOW)

    assert restored["privacy"] == "private"
    assert restored["expires_at"] == "2026-08-01T00:00:00+00:00"
    assert restored["pinned"] is False
