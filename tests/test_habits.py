from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier

import pytest

from nexus.habits import HabitService
from nexus.store import JsonStore


NOW = datetime(2026, 8, 8, 8, 0, tzinfo=UTC)


def service(tmp_path: Path) -> HabitService:
    return HabitService(JsonStore(tmp_path / "state.json"), timezone="UTC")


def test_add_validates_cadence_target_and_linked_goal(tmp_path: Path) -> None:
    habits = service(tmp_path)

    with pytest.raises(ValueError, match="cadence"):
        habits.add("Read", "", "monthly", (), 1, None, now=NOW)
    with pytest.raises(ValueError, match="target_count"):
        habits.add("Read", "", "daily", (), 0, None, now=NOW)
    with pytest.raises(ValueError, match="weekdays"):
        habits.add("Read", "", "weekdays", (0, 8), 1, None, now=NOW)

    created = habits.add(
        "Read papers",
        "Read one research paper",
        "weekdays",
        (1, 3, 6),
        1,
        "goal-1",
        now=NOW,
    )
    assert created["name"] == "Read papers"
    assert created["cadence"] == "weekdays"
    assert created["weekdays"] == [1, 3, 6]
    assert created["goal_id"] == "goal-1"
    assert created["check_ins"] == []


def test_same_day_check_in_updates_in_place_and_derives_summary(tmp_path: Path) -> None:
    habits = service(tmp_path)
    habit = habits.add("Read", "", "daily", (), 2, None, now=NOW)

    habits.check_in(habit["id"], "2026-08-08", 1, "morning", now=NOW)
    result = habits.check_in(habit["id"], "2026-08-08", 2, "evening", now=NOW)

    assert result["summary"]["today_count"] == 2
    assert result["summary"]["today_complete"] is True
    assert result["summary"]["streak"] == 1
    assert result["summary"]["completion_rate"] == 1.0
    assert len(result["habit"]["check_ins"]) == 1
    assert result["habit"]["check_ins"][0]["note"] == "evening"


def test_increment_check_in_adds_to_latest_persisted_count(tmp_path: Path) -> None:
    habits = service(tmp_path)
    habit = habits.add("Read", "", "daily", (), 3, None, now=NOW)
    habits.check_in(habit["id"], "2026-08-08", 2, "other client", now=NOW)

    result = habits.increment_check_in(
        habit["id"], "2026-08-08", 1, "Dashboard check-in", now=NOW
    )

    assert result["summary"]["today_count"] == 3
    assert result["summary"]["today_complete"] is True


def test_weekday_streak_skips_days_that_are_not_scheduled(tmp_path: Path) -> None:
    habits = service(tmp_path)
    habit = habits.add("Train", "", "weekdays", (1, 3, 5), 1, None, now=NOW)
    for day in ("2026-08-03", "2026-08-05", "2026-08-07"):
        habits.check_in(habit["id"], day, 1, "", now=NOW)

    listed = habits.list(now=NOW)

    assert listed[0]["summary"]["due_today"] is False
    assert listed[0]["summary"]["streak"] == 3
    assert listed[0]["summary"]["completion_rate"] == 1.0


def test_archive_hides_habit_by_default_and_legacy_state_normalizes(
    tmp_path: Path,
) -> None:
    store = JsonStore(tmp_path / "state.json")
    assert store.load()["habits"] == []
    habits = HabitService(store, timezone="UTC")
    habit = habits.add("Sleep", "", "daily", (), 1, None, now=NOW)

    archived = habits.archive(habit["id"], now=NOW)

    assert archived["status"] == "archived"
    assert habits.list(now=NOW) == []
    assert habits.list(now=NOW, include_archived=True)[0]["id"] == habit["id"]


def test_concurrent_check_ins_preserve_both_dates(tmp_path: Path) -> None:
    habits = service(tmp_path)
    habit = habits.add("Walk", "", "daily", (), 1, None, now=NOW)
    barrier = Barrier(3)

    def check_in(day: str) -> None:
        barrier.wait()
        habits.check_in(habit["id"], day, 1, day, now=NOW)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(check_in, day) for day in ("2026-08-07", "2026-08-08")
        ]
        barrier.wait()
        for future in futures:
            future.result()

    stored = habits.list(now=NOW)[0]["check_ins"]
    assert [item["date"] for item in stored] == ["2026-08-07", "2026-08-08"]


def test_check_in_rejects_unknown_habit_invalid_date_and_negative_count(
    tmp_path: Path,
) -> None:
    habits = service(tmp_path)
    habit = habits.add("Walk", "", "daily", (), 1, None, now=NOW)

    with pytest.raises(ValueError, match="not found"):
        habits.check_in("missing", "2026-08-08", 1, "", now=NOW)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        habits.check_in(habit["id"], "08/08/2026", 1, "", now=NOW)
    with pytest.raises(ValueError, match="count"):
        habits.check_in(habit["id"], "2026-08-08", -1, "", now=NOW)
