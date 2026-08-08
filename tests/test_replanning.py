from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.replanning import ReplanningService
from nexus.store import JsonStore


NOW = datetime(2026, 8, 8, 8, 0, tzinfo=UTC)


def make_service(tmp_path: Path, tasks: list[dict]) -> ReplanningService:
    store = JsonStore(tmp_path / "state.json")
    state = store.load()
    state["daily_tasks"] = tasks
    store.save(state)
    return ReplanningService(store, timezone="UTC")


def task(
    task_id: str, priority: int, minutes: int, status: str = "pending", **extra: object
) -> dict:
    return {
        "id": task_id,
        "title": task_id,
        "plan_date": "2026-08-08",
        "priority": priority,
        "estimated_minutes": minutes,
        "status": status,
        "blocker": None,
        **extra,
    }


def test_preview_respects_events_priority_status_and_capacity(tmp_path: Path) -> None:
    service = make_service(
        tmp_path,
        [
            task("done", 1, 30, "completed"),
            task(
                "active",
                1,
                60,
                "in_progress",
                scheduled_start="2026-08-08T09:00:00+00:00",
                scheduled_end="2026-08-08T10:00:00+00:00",
            ),
            task("high", 1, 120),
            task("long", 2, 300),
            task("last", 3, 30),
        ],
    )
    events = [
        {
            "start": "2026-08-08T10:00:00+00:00",
            "end": "2026-08-08T11:00:00+00:00",
            "summary": "Meeting",
            "all_day": False,
        }
    ]

    preview = service.preview("2026-08-08", events, ("09:00", "17:00"), now=NOW)

    assert {item["task_id"] for item in preview["kept"]} == {"done", "active"}
    assert preview["moved"][0]["task_id"] == "high"
    assert preview["moved"][0]["scheduled_start"] == "2026-08-08T11:00:00+00:00"
    assert preview["shortened"][0]["task_id"] == "long"
    assert preview["unscheduled"][0]["task_id"] == "last"


def test_overlapping_and_all_day_events_are_immutable_constraints(
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path, [task("one", 1, 30)])
    events = [
        {
            "start": "2026-08-08T08:00:00+00:00",
            "end": "2026-08-08T12:00:00+00:00",
            "all_day": False,
        },
        {
            "start": "2026-08-08T11:00:00+00:00",
            "end": "2026-08-08T13:00:00+00:00",
            "all_day": False,
        },
    ]
    preview = service.preview("2026-08-08", events, ("09:00", "17:00"), now=NOW)
    assert preview["moved"][0]["scheduled_start"] == "2026-08-08T13:00:00+00:00"

    blocked = service.preview(
        "2026-08-08",
        [{"start": "2026-08-08", "end": "2026-08-09", "all_day": True}],
        ("09:00", "17:00"),
        now=NOW,
    )
    assert blocked["unscheduled"][0]["reason"] == "no_free_window"


def test_calendar_failure_degrades_to_task_only_plan(tmp_path: Path) -> None:
    service = make_service(tmp_path, [task("one", 1, 30)])
    preview = service.preview("2026-08-08", None, ("09:00", "17:00"), now=NOW)
    assert preview["degradations"] == ["calendar_unavailable"]
    assert preview["moved"][0]["scheduled_start"] == "2026-08-08T09:00:00+00:00"


def test_apply_updates_only_schedule_fields_and_rejects_stale_inputs(
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path, [task("one", 1, 30)])
    events: list[dict] = []
    preview = service.preview("2026-08-08", events, ("09:00", "17:00"), now=NOW)
    applied = service.apply(preview, events, now=NOW)
    stored = service.store.load()["daily_tasks"][0]
    assert applied["updated_task_ids"] == ["one"]
    assert stored["title"] == "one"
    assert stored["status"] == "pending"
    assert stored["scheduled_start"] == "2026-08-08T09:00:00+00:00"

    with pytest.raises(ValueError, match="calendar"):
        service.apply(
            preview,
            [
                {
                    "start": "2026-08-08T10:00:00+00:00",
                    "end": "2026-08-08T11:00:00+00:00",
                }
            ],
            now=NOW,
        )

    newer = service.preview("2026-08-08", events, ("09:00", "17:00"), now=NOW)
    state = service.store.load()
    state["goals"].append({"id": "changed"})
    service.store.save(state)
    with pytest.raises(ValueError, match="state"):
        service.apply(newer, events, now=NOW)
