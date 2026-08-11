from __future__ import annotations

from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .store import JsonStore


HABIT_CADENCES = ("daily", "weekdays")
MAX_HABITS = 200
MAX_CHECK_INS = 400
MAX_TEXT_LENGTH = 500


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(microsecond=0).isoformat()


def _bounded_text(value: str, field: str, *, required: bool = False) -> str:
    text = str(value).strip()
    if required and not text:
        raise ValueError(f"{field} is required.")
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"{field} must be at most {MAX_TEXT_LENGTH} characters.")
    return text


def _parse_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("date must use YYYY-MM-DD.") from exc
    if parsed.isoformat() != value:
        raise ValueError("date must use YYYY-MM-DD.")
    return parsed


def _is_due(habit: dict[str, Any], value: date) -> bool:
    return habit.get("cadence") == "daily" or value.isoweekday() in set(
        habit.get("weekdays", [])
    )


def habit_summary(
    habit: dict[str, Any],
    today: date,
    *,
    window_days: int = 30,
) -> dict[str, Any]:
    check_ins = {
        item["date"]: int(item.get("count", 0))
        for item in habit.get("check_ins", [])
        if isinstance(item, dict) and isinstance(item.get("date"), str)
    }
    target = int(habit.get("target_count", 1))
    cursor = today
    while not _is_due(habit, cursor):
        cursor -= timedelta(days=1)

    streak = 0
    streak_cursor = cursor
    for _ in range(MAX_CHECK_INS):
        if check_ins.get(streak_cursor.isoformat(), 0) < target:
            break
        streak += 1
        streak_cursor -= timedelta(days=1)
        while not _is_due(habit, streak_cursor):
            streak_cursor -= timedelta(days=1)

    parsed_dates = []
    for value in check_ins:
        try:
            parsed_dates.append(date.fromisoformat(value))
        except ValueError:
            continue
    earliest = min(parsed_dates, default=cursor)
    scheduled: list[date] = []
    completion_cursor = cursor
    while completion_cursor >= earliest and len(scheduled) < window_days:
        if _is_due(habit, completion_cursor):
            scheduled.append(completion_cursor)
        completion_cursor -= timedelta(days=1)
    if not scheduled:
        scheduled = [cursor]
    completed = sum(check_ins.get(item.isoformat(), 0) >= target for item in scheduled)
    today_count = check_ins.get(today.isoformat(), 0)
    return {
        "due_today": _is_due(habit, today),
        "today_count": today_count,
        "today_complete": today_count >= target,
        "streak": streak,
        "completion_rate": round(completed / len(scheduled), 4),
        "scheduled_days": len(scheduled),
        "completed_days": completed,
    }


class HabitService:
    def __init__(self, store: JsonStore, *, timezone: str = "UTC") -> None:
        self.store = store
        try:
            self.timezone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be an IANA timezone name.") from exc

    def add(
        self,
        name: str,
        description: str,
        cadence: str,
        weekdays: tuple[int, ...] | list[int],
        target_count: int,
        goal_id: str | None,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        clean_name = _bounded_text(name, "name", required=True)
        clean_description = _bounded_text(description, "description")
        if cadence not in HABIT_CADENCES:
            raise ValueError("cadence must be 'daily' or 'weekdays'.")
        if (
            not isinstance(target_count, int)
            or isinstance(target_count, bool)
            or not 1 <= target_count <= 100
        ):
            raise ValueError("target_count must be an integer from 1 to 100.")
        normalized_weekdays = sorted(set(weekdays))
        if cadence == "weekdays":
            if not normalized_weekdays or any(
                not isinstance(item, int)
                or isinstance(item, bool)
                or item < 1
                or item > 7
                for item in normalized_weekdays
            ):
                raise ValueError(
                    "weekdays must contain ISO weekday values from 1 to 7."
                )
        else:
            normalized_weekdays = []
        timestamp = _iso_utc(now or datetime.now(UTC))
        habit = {
            "id": uuid4().hex[:8],
            "name": clean_name,
            "description": clean_description,
            "goal_id": str(goal_id).strip()[:100] if goal_id else None,
            "cadence": cadence,
            "weekdays": normalized_weekdays,
            "target_count": target_count,
            "status": "active",
            "created_at": timestamp,
            "archived_at": None,
            "check_ins": [],
        }

        def mutation(state: dict[str, Any]) -> dict[str, Any]:
            collection = state.setdefault("habits", [])
            if len(collection) >= MAX_HABITS:
                raise ValueError(f"At most {MAX_HABITS} habits are supported.")
            collection.append(deepcopy(habit))
            return deepcopy(habit)

        return self.store.mutate(mutation)

    def list(
        self,
        *,
        now: datetime | None = None,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        today = current.astimezone(self.timezone).date()
        items = []
        for raw in self.store.load().get("habits", []):
            if not isinstance(raw, dict):
                continue
            if not include_archived and raw.get("status") != "active":
                continue
            habit = deepcopy(raw)
            habit["summary"] = habit_summary(habit, today)
            items.append(habit)
        return sorted(
            items,
            key=lambda item: (item.get("status") != "active", item["name"].casefold()),
        )

    def check_in(
        self,
        habit_id: str,
        local_date: str,
        count: int,
        note: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        checked_date = _parse_date(local_date)
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
            or count > 1000
        ):
            raise ValueError("count must be an integer from 0 to 1000.")
        clean_note = _bounded_text(note, "note")
        timestamp = _iso_utc(now or datetime.now(UTC))

        def mutation(state: dict[str, Any]) -> dict[str, Any]:
            for habit in state.setdefault("habits", []):
                if habit.get("id") != habit_id:
                    continue
                if habit.get("status") != "active":
                    raise ValueError(f"Habit '{habit_id}' is archived.")
                record = {
                    "date": checked_date.isoformat(),
                    "count": count,
                    "note": clean_note,
                    "at": timestamp,
                }
                check_ins = habit.setdefault("check_ins", [])
                for index, existing in enumerate(check_ins):
                    if existing.get("date") == record["date"]:
                        check_ins[index] = record
                        break
                else:
                    check_ins.append(record)
                check_ins.sort(key=lambda item: item.get("date", ""))
                del check_ins[:-MAX_CHECK_INS]
                return deepcopy(habit)
            raise ValueError(f"Habit '{habit_id}' not found.")

        habit = self.store.mutate(mutation)
        return {"habit": habit, "summary": habit_summary(habit, checked_date)}

    def increment_check_in(
        self,
        habit_id: str,
        local_date: str,
        increment: int,
        note: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        checked_date = _parse_date(local_date)
        if (
            not isinstance(increment, int)
            or isinstance(increment, bool)
            or increment < 1
            or increment > 1000
        ):
            raise ValueError("increment must be an integer from 1 to 1000.")
        clean_note = _bounded_text(note, "note")
        timestamp = _iso_utc(now or datetime.now(UTC))

        def mutation(state: dict[str, Any]) -> dict[str, Any]:
            for habit in state.setdefault("habits", []):
                if habit.get("id") != habit_id:
                    continue
                if habit.get("status") != "active":
                    raise ValueError(f"Habit '{habit_id}' is archived.")
                check_ins = habit.setdefault("check_ins", [])
                existing = next(
                    (
                        item
                        for item in check_ins
                        if item.get("date") == checked_date.isoformat()
                    ),
                    None,
                )
                count = (
                    int(existing.get("count", 0)) + increment if existing else increment
                )
                if count > 1000:
                    raise ValueError("habit count cannot exceed 1000.")
                record = {
                    "date": checked_date.isoformat(),
                    "count": count,
                    "note": clean_note,
                    "at": timestamp,
                }
                if existing is None:
                    check_ins.append(record)
                else:
                    check_ins[check_ins.index(existing)] = record
                check_ins.sort(key=lambda item: item.get("date", ""))
                del check_ins[:-MAX_CHECK_INS]
                return deepcopy(habit)
            raise ValueError(f"Habit '{habit_id}' not found.")

        habit = self.store.mutate(mutation)
        return {"habit": habit, "summary": habit_summary(habit, checked_date)}

    def archive(
        self,
        habit_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = _iso_utc(now or datetime.now(UTC))

        def mutation(state: dict[str, Any]) -> dict[str, Any]:
            for habit in state.setdefault("habits", []):
                if habit.get("id") == habit_id:
                    habit["status"] = "archived"
                    habit["archived_at"] = timestamp
                    return deepcopy(habit)
            raise ValueError(f"Habit '{habit_id}' not found.")

        return self.store.mutate(mutation)
