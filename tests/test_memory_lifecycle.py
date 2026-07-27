from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from nexus.memory_lifecycle import (
    MemoryLifecycleError,
    apply_transition,
    build_compression_plan,
    detect_duplicate,
    is_memory_eligible,
    normalize_memory,
    score_importance,
)


NOW = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)


def memory(memory_id: str, text: str, **overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": memory_id,
        "text": text,
        "tags": ["project"],
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    record.update(overrides)
    return record


def test_importance_scoring_is_deterministic_bounded_and_signal_aware() -> None:
    ordinary = score_importance("Read one chapter", ["reading"])
    significant = score_importance(
        "Important deadline: submit the overseas AI master application tomorrow",
        ["deadline", "goal", "education"],
    )

    assert 0.1 <= ordinary <= 0.9
    assert 0.1 <= significant <= 0.9
    assert significant > ordinary
    assert significant == score_importance(
        "Important deadline: submit the overseas AI master application tomorrow",
        ["deadline", "goal", "education"],
    )


def test_normalize_memory_adds_compatible_lifecycle_defaults() -> None:
    normalized = normalize_memory(memory("m1", "Build Nexus"), now=NOW)

    assert normalized["importance_source"] == "automatic"
    assert 0.0 <= normalized["importance"] <= 1.0
    assert normalized["privacy"] == "private"
    assert normalized["status"] == "active"
    assert normalized["pinned"] is False
    assert normalized["conflicts_with"] == []
    assert normalized["updated_at"] == "2026-01-01T00:00:00+00:00"


def test_normalize_rejects_invalid_lifecycle_values() -> None:
    with pytest.raises(MemoryLifecycleError, match="privacy"):
        normalize_memory(memory("m1", "Build Nexus", privacy="public"), now=NOW)
    with pytest.raises(MemoryLifecycleError, match="importance"):
        normalize_memory(memory("m1", "Build Nexus", importance=1.5), now=NOW)


def test_duplicate_detection_distinguishes_exact_near_and_unique() -> None:
    memories = [
        normalize_memory(memory("m1", "Prepare IELTS listening every day"), now=NOW),
    ]

    exact = detect_duplicate(
        memories, "  prepare IELTS listening every day! ", ["project"]
    )
    near = detect_duplicate(
        memories, "Prepare IELTS listening practice every day", ["ielts"]
    )
    unique = detect_duplicate(memories, "Buy groceries for breakfast", ["home"])

    assert exact.kind == "exact"
    assert exact.memory_id == "m1"
    assert exact.similarity == 1.0
    assert near.kind == "near"
    assert near.memory_id == "m1"
    assert 0.75 <= near.similarity < 1.0
    assert unique.kind == "none"


def test_eligibility_respects_status_expiry_pin_and_privacy() -> None:
    active_private = normalize_memory(
        memory("m1", "Private", privacy="private"), now=NOW
    )
    shared = normalize_memory(memory("m2", "Shared", privacy="shared"), now=NOW)
    archived = normalize_memory(memory("m3", "Archived", status="archived"), now=NOW)
    expired = normalize_memory(
        memory("m4", "Expired", expires_at="2026-07-26T00:00:00+00:00"),
        now=NOW,
    )
    pinned_expired = normalize_memory(
        memory("m5", "Pinned", expires_at="2026-07-26T00:00:00+00:00", pinned=True),
        now=NOW,
    )

    assert is_memory_eligible(active_private, privacy="private", now=NOW)
    assert not is_memory_eligible(active_private, privacy="shared", now=NOW)
    assert is_memory_eligible(shared, privacy="private", now=NOW)
    assert is_memory_eligible(shared, privacy="shared", now=NOW)
    assert not is_memory_eligible(archived, privacy="private", now=NOW)
    assert is_memory_eligible(
        archived, privacy="private", include_archived=True, now=NOW
    )
    assert not is_memory_eligible(expired, privacy="private", now=NOW)
    assert is_memory_eligible(pinned_expired, privacy="private", now=NOW)


def test_transitions_are_reversible_and_record_timestamps() -> None:
    active = normalize_memory(memory("m1", "Build Nexus"), now=NOW)
    archived = apply_transition(active, "archive", now=NOW)
    restored = apply_transition(archived, "restore", now=NOW + timedelta(hours=1))
    forgotten = apply_transition(restored, "forget", now=NOW + timedelta(hours=2))

    assert archived["status"] == "archived"
    assert archived["archived_at"] == "2026-07-27T08:00:00+00:00"
    assert restored["status"] == "active"
    assert restored["archived_at"] is None
    assert forgotten["status"] == "forgotten"
    assert forgotten["forgotten_at"] == "2026-07-27T10:00:00+00:00"
    assert apply_transition(forgotten, "restore", now=NOW)["status"] == "active"


def test_compression_plan_groups_old_low_importance_memories() -> None:
    records = [
        normalize_memory(memory("m1", "Read paper A", importance=0.2), now=NOW),
        normalize_memory(memory("m2", "Read paper B", importance=0.3), now=NOW),
        normalize_memory(
            memory("m3", "Pinned fact", importance=0.1, pinned=True),
            now=NOW,
        ),
        normalize_memory(
            memory(
                "m4",
                "Recent note",
                importance=0.1,
                created_at="2026-07-26T00:00:00+00:00",
            ),
            now=NOW,
        ),
    ]

    plan = build_compression_plan(
        records,
        older_than_days=90,
        max_importance=0.4,
        now=NOW,
        minimum_group_size=2,
    )

    assert len(plan) == 1
    assert plan[0].source_ids == ["m1", "m2"]
    assert "Read paper A" in plan[0].summary_text
    assert "Read paper B" in plan[0].summary_text
