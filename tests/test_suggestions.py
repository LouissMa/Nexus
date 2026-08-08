from __future__ import annotations

import json

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.store import JsonStore
from nexus.suggestions import (
    SuggestionEngine,
    SuggestionService,
    SuggestionWordingAdapter,
)


NOW = datetime(2026, 8, 8, 9, 0, tzinfo=UTC)


def populated_state() -> dict:
    return {
        "goals": [
            {
                "id": "g1",
                "title": "Nexus",
                "status": "active",
                "cadence_days": 3,
                "created_at": "2026-08-01T09:00:00+00:00",
                "last_check_in": None,
            }
        ],
        "daily_tasks": [
            {
                "id": "t1",
                "title": "Fix retrieval",
                "status": "blocked",
                "blocker": "Need benchmark",
                "priority": 1,
                "plan_date": "2026-08-08",
            }
        ],
        "habits": [
            {
                "id": "h1",
                "name": "Read",
                "status": "active",
                "cadence": "daily",
                "weekdays": [],
                "target_count": 1,
                "check_ins": [],
            }
        ],
        "projects": [
            {
                "id": "p1",
                "name": "Nexus",
                "status": "active",
                "priority": 1,
                "target_date": "2026-08-20",
                "milestones": [
                    {
                        "id": "m1",
                        "title": "Dashboard",
                        "status": "pending",
                        "target_date": "2026-08-10",
                    }
                ],
            }
        ],
        "suggestions": [],
    }


def test_engine_generates_ranked_explainable_stable_suggestions() -> None:
    engine = SuggestionEngine(timezone="UTC")
    first = engine.generate(populated_state(), NOW)
    second = engine.generate(populated_state(), NOW)

    assert [item["id"] for item in first] == [item["id"] for item in second]
    assert {item["kind"] for item in first} >= {
        "blocked_task",
        "quiet_goal",
        "habit_risk",
        "milestone_deadline",
    }
    assert first[0]["kind"] == "blocked_task"
    assert all(item["reason"] and item["source_ids"] for item in first)
    assert all(0 <= item["confidence"] <= 1 for item in first)


def test_service_refresh_expiry_dismiss_and_accept_allowlist(tmp_path: Path) -> None:
    store = JsonStore(tmp_path / "state.json")
    state = store.load()
    state.update(populated_state())
    store.save(state)
    service = SuggestionService(store, timezone="UTC")

    suggestions = service.list(now=NOW, refresh=True)
    quiet = next(item for item in suggestions if item["kind"] == "quiet_goal")
    with pytest.raises(ValueError, match="approval"):
        service.accept(quiet["id"], approved=False, now=NOW)

    accepted = service.accept(quiet["id"], approved=True, now=NOW)
    assert accepted["suggestion"]["status"] == "accepted"
    assert accepted["action_result"]["task"]["goal_id"] == "g1"

    habit = next(item for item in suggestions if item["kind"] == "habit_risk")
    dismissed = service.dismiss(habit["id"], now=NOW)
    assert dismissed["status"] == "dismissed"

    late = datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
    assert service.list(now=late, refresh=False) == []


def test_accept_rejects_tampered_action_and_unknown_id(tmp_path: Path) -> None:
    store = JsonStore(tmp_path / "state.json")
    state = store.load()
    state["suggestions"] = [
        {
            "id": "bad",
            "kind": "bad",
            "title": "Bad",
            "reason": "Bad",
            "action": {"type": "shell", "command": "whoami"},
            "confidence": 1.0,
            "source_ids": ["x"],
            "created_at": "2026-08-08T09:00:00+00:00",
            "expires_at": "2026-08-09T09:00:00+00:00",
            "status": "open",
        }
    ]
    store.save(state)
    service = SuggestionService(store)

    with pytest.raises(ValueError, match="not allowed"):
        service.accept("bad", approved=True, now=NOW)
    with pytest.raises(ValueError, match="not found"):
        service.dismiss("missing", now=NOW)


def test_llm_wording_adapter_cannot_change_structured_decisions() -> None:
    original = SuggestionEngine().generate(populated_state(), NOW, limit=1)

    class FakeLLM:
        def generate(self, _system: str, _user: str) -> str:
            item = original[0]
            return json.dumps(
                [
                    {
                        "id": item["id"],
                        "title": "Clear the blocker",
                        "reason": "A dependency is stopping progress.",
                    }
                ]
            )

    rewritten = SuggestionWordingAdapter.rewrite(original, FakeLLM())

    assert rewritten[0]["title"] == "Clear the blocker"
    assert rewritten[0]["action"] == original[0]["action"]
    assert rewritten[0]["source_ids"] == original[0]["source_ids"]
    assert rewritten[0]["confidence"] == original[0]["confidence"]
