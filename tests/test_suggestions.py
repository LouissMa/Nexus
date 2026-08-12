from __future__ import annotations

import json

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nexus.store import JsonStore
from nexus.service import NexusService
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


def test_engine_adds_calendar_conflict_focus_window_and_rag_memory_candidates() -> None:
    state = populated_state()
    state["daily_tasks"][0].update(
        {
            "status": "pending",
            "blocker": None,
            "scheduled_start": "2026-08-08T09:30:00+00:00",
            "scheduled_end": "2026-08-08T10:30:00+00:00",
        }
    )
    calendar = [
        {
            "summary": "Research meeting",
            "start": "2026-08-08T09:00:00+00:00",
            "end": "2026-08-08T10:00:00+00:00",
            "all_day": False,
        }
    ]
    memories = [
        {
            "id": "mem-1",
            "text": "Benchmark retrieval quality before changing the ranking model.",
            "retrieval_score": 0.91,
        }
    ]

    suggestions = SuggestionEngine(timezone="UTC").generate(
        state, NOW, calendar=calendar, memories=memories, limit=20
    )
    by_kind = {item["kind"]: item for item in suggestions}

    assert by_kind["calendar_conflict"]["source_types"] == ["calendar", "task"]
    assert "Research meeting" in by_kind["calendar_conflict"]["reason"]
    assert by_kind["calendar_focus_window"]["source_types"] == ["calendar"]
    assert by_kind["relevant_memory"]["source_ids"] == ["memory:mem-1"]
    assert "Benchmark retrieval quality" in by_kind["relevant_memory"]["reason"]


def test_engine_ignores_invalid_calendar_and_memory_context() -> None:
    suggestions = SuggestionEngine(timezone="UTC").generate(
        populated_state(),
        NOW,
        calendar=[{"summary": "broken", "start": "nope", "end": "still-nope"}],
        memories=[{"id": "missing-text"}, {"text": "missing id"}],
    )

    assert not {
        "calendar_conflict",
        "calendar_focus_window",
        "relevant_memory",
    }.intersection(item["kind"] for item in suggestions)


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


def test_service_refresh_persists_context_status_and_enriched_sources(
    tmp_path: Path,
) -> None:
    store = JsonStore(tmp_path / "state.json")
    state = store.load()
    state.update(populated_state())
    store.save(state)
    service = SuggestionService(store, timezone="UTC")

    suggestions = service.list(
        now=NOW,
        refresh=True,
        calendar=[],
        memories=[
            {"id": "mem-1", "text": "Review the benchmark", "retrieval_score": 0.8}
        ],
        context={"calendar": "available", "rag": "available", "degradations": []},
    )

    memory = next(item for item in suggestions if item["kind"] == "relevant_memory")
    assert memory["context"] == {
        "calendar": "available",
        "rag": "available",
        "degradations": [],
    }
    assert store.load()["suggestion_context"] == memory["context"]


def test_nexus_service_refresh_uses_rag_and_reports_context(tmp_path: Path) -> None:
    service = NexusService(JsonStore(tmp_path / "state.json"))
    service.add_goal("Improve Nexus retrieval", "Benchmark ranking quality", 1)
    memory = service.add_memory(
        "Run the retrieval benchmark before changing ranking weights.",
        ["nexus", "retrieval"],
        now=NOW,
    )

    suggestions = service.list_suggestions(
        timezone="UTC", now=NOW + timedelta(days=2), refresh=True, calendar=[]
    )
    relevant = next(item for item in suggestions if item["kind"] == "relevant_memory")

    assert relevant["source_ids"] == [f"memory:{memory.id}"]
    assert service.suggestion_context() == {
        "calendar": "available",
        "rag": "available",
        "degradations": [],
    }


def test_nexus_service_keeps_base_suggestions_when_rag_fails(tmp_path: Path) -> None:
    class BrokenRetriever:
        def retrieve_result(self, *_args, **_kwargs):
            raise RuntimeError("vector store unavailable")

    service = NexusService(
        JsonStore(tmp_path / "state.json"), memory_retriever=BrokenRetriever()
    )
    service.add_goal("Build Nexus", "Continue implementation", 1)

    suggestions = service.list_suggestions(
        timezone="UTC",
        now=datetime(2030, 8, 10, 9, 0, tzinfo=UTC),
        refresh=True,
        calendar=None,
        calendar_requested=True,
    )

    assert any(item["kind"] == "quiet_goal" for item in suggestions)
    assert service.suggestion_context() == {
        "calendar": "unavailable",
        "rag": "unavailable",
        "degradations": ["calendar_unavailable", "rag_unavailable"],
    }


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
