from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .store import JsonStore

MIN_SLOT_MINUTES = 15
MAX_TASKS = 200
MAX_EVENTS = 500


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


def _parse_clock(value: str) -> time:
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("working hours must use HH:MM.") from exc
    if parsed.second or parsed.microsecond:
        raise ValueError("working hours must use HH:MM.")
    return parsed


def _hash(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ReplanningService:
    def __init__(self, store: JsonStore, *, timezone: str = "UTC") -> None:
        self.store = store
        try:
            self.timezone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be an IANA timezone name.") from exc

    def preview(
        self,
        plan_date: str,
        events: list[dict[str, Any]] | None,
        working_hours: tuple[str, str],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        try:
            day = date.fromisoformat(plan_date)
        except ValueError as exc:
            raise ValueError("plan_date must use YYYY-MM-DD.") from exc
        start_clock, end_clock = map(_parse_clock, working_hours)
        day_start = datetime.combine(day, start_clock, self.timezone)
        day_end = datetime.combine(day, end_clock, self.timezone)
        if day_end <= day_start:
            raise ValueError("working end must be after working start.")
        degradations = ["calendar_unavailable"] if events is None else []
        normalized_events = self._normalize_events(events or [], day_start, day_end)
        state = self.store.load()
        tasks = [
            deepcopy(item)
            for item in state.get("daily_tasks", [])[:MAX_TASKS]
            if isinstance(item, dict) and item.get("plan_date") == plan_date
        ]
        free = self._free_windows(day_start, day_end, normalized_events)
        kept: list[dict[str, Any]] = []
        movable: list[dict[str, Any]] = []
        for task in tasks:
            if task.get("status") == "completed":
                kept.append({"task_id": task.get("id"), "reason": "completed"})
                continue
            if task.get("status") == "in_progress":
                interval = self._task_interval(task)
                if interval and self._interval_is_free(interval, free):
                    free = self._reserve(free, interval)
                    kept.append(
                        {
                            "task_id": task.get("id"),
                            "reason": "in_progress",
                            "scheduled_start": _iso(interval[0]),
                            "scheduled_end": _iso(interval[1]),
                        }
                    )
                    continue
            if task.get("status") in {"pending", "in_progress", "blocked"}:
                movable.append(task)
        movable.sort(
            key=lambda item: (
                item.get("status") != "in_progress",
                self._priority(item.get("priority")),
                str(item.get("id", "")),
            )
        )
        moved: list[dict[str, Any]] = []
        shortened: list[dict[str, Any]] = []
        unscheduled: list[dict[str, Any]] = []
        updates: list[dict[str, Any]] = []
        for task in movable:
            minutes = self._minutes(task.get("estimated_minutes", 30))
            allocation, was_shortened = self._allocate(free, minutes)
            if allocation is None:
                item = {"task_id": task.get("id"), "reason": "no_free_window"}
                unscheduled.append(item)
                updates.append({**item, "scheduled_start": None, "scheduled_end": None})
                continue
            free = self._reserve(free, allocation)
            item = {
                "task_id": task.get("id"),
                "scheduled_start": _iso(allocation[0]),
                "scheduled_end": _iso(allocation[1]),
                "estimated_minutes": minutes,
                "scheduled_minutes": int(
                    (allocation[1] - allocation[0]).total_seconds() // 60
                ),
                "reason": "insufficient_contiguous_time"
                if was_shortened
                else "priority_allocation",
            }
            (shortened if was_shortened else moved).append(item)
            updates.append(item)
        preview = {
            "state_revision": state.revision,
            "calendar_fingerprint": _hash(normalized_events),
            "plan_date": plan_date,
            "working_hours": list(working_hours),
            "kept": kept,
            "moved": moved,
            "shortened": shortened,
            "unscheduled": unscheduled,
            "updates": updates,
            "degradations": degradations,
            "created_at": _iso(_aware(now or datetime.now(UTC))),
        }
        preview["id"] = _hash(preview)[:16]
        return preview

    def apply(
        self,
        preview: dict[str, Any],
        events: list[dict[str, Any]] | None,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not isinstance(preview, dict) or not isinstance(preview.get("id"), str):
            raise ValueError("preview must be a valid replan preview.")
        integrity = deepcopy(preview)
        preview_id = integrity.pop("id")
        if _hash(integrity)[:16] != preview_id:
            raise ValueError("preview integrity check failed.")
        try:
            day = date.fromisoformat(preview["plan_date"])
            start_clock, end_clock = map(_parse_clock, preview["working_hours"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("preview contains invalid planning fields.") from exc
        normalized = self._normalize_events(
            events or [],
            datetime.combine(day, start_clock, self.timezone),
            datetime.combine(day, end_clock, self.timezone),
        )
        if _hash(normalized) != preview.get("calendar_fingerprint"):
            raise ValueError("calendar changed since this preview was created.")
        timestamp = _iso(_aware(now or datetime.now(UTC)))

        def mutation(state: dict[str, Any]) -> list[str]:
            if getattr(state, "revision", None) != preview.get("state_revision"):
                raise ValueError("state changed since this preview was created.")
            updates = {
                item.get("task_id"): item
                for item in preview.get("updates", [])
                if isinstance(item, dict) and item.get("task_id")
            }
            changed: list[str] = []
            for task in state.get("daily_tasks", []):
                update = updates.get(task.get("id"))
                if update is None:
                    continue
                task["scheduled_start"] = update.get("scheduled_start")
                task["scheduled_end"] = update.get("scheduled_end")
                task["schedule_status"] = (
                    "unscheduled"
                    if update.get("scheduled_start") is None
                    else "scheduled"
                )
                task["schedule_reason"] = update.get("reason")
                task["schedule_updated_at"] = timestamp
                changed.append(task["id"])
            return changed

        changed = self.store.mutate(mutation)
        return {
            "preview_id": preview_id,
            "updated_task_ids": changed,
            "applied_at": timestamp,
        }

    def _normalize_events(
        self, events: list[dict[str, Any]], day_start: datetime, day_end: datetime
    ) -> list[dict[str, str]]:
        if not isinstance(events, list) or len(events) > MAX_EVENTS:
            raise ValueError(f"events must be a list with at most {MAX_EVENTS} items.")
        intervals: list[tuple[datetime, datetime]] = []
        for event in events:
            if not isinstance(event, dict):
                raise ValueError("each calendar event must be an object.")
            if event.get("all_day"):
                try:
                    start_day = date.fromisoformat(str(event.get("start"))[:10])
                    end_day = date.fromisoformat(str(event.get("end"))[:10])
                except ValueError as exc:
                    raise ValueError(
                        "calendar event dates must be ISO values."
                    ) from exc
                if (
                    start_day
                    <= day_start.date()
                    < max(end_day, start_day + timedelta(days=1))
                ):
                    intervals.append((day_start, day_end))
                continue
            try:
                start = _aware(
                    datetime.fromisoformat(str(event.get("start")))
                ).astimezone(self.timezone)
                end = _aware(datetime.fromisoformat(str(event.get("end")))).astimezone(
                    self.timezone
                )
            except ValueError as exc:
                raise ValueError(
                    "calendar event times must be ISO timestamps."
                ) from exc
            if end > start:
                clipped = (max(start, day_start), min(end, day_end))
                if clipped[1] > clipped[0]:
                    intervals.append(clipped)
        intervals.sort()
        merged: list[list[datetime]] = []
        for start, end in intervals:
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        return [{"start": _iso(start), "end": _iso(end)} for start, end in merged]

    @staticmethod
    def _free_windows(
        day_start: datetime, day_end: datetime, events: list[dict[str, str]]
    ) -> list[tuple[datetime, datetime]]:
        free = [(day_start, day_end)]
        for event in events:
            free = ReplanningService._reserve(
                free,
                (
                    datetime.fromisoformat(event["start"]),
                    datetime.fromisoformat(event["end"]),
                ),
            )
        return free

    def _task_interval(self, task: dict[str, Any]) -> tuple[datetime, datetime] | None:
        try:
            start = _aware(
                datetime.fromisoformat(str(task.get("scheduled_start")))
            ).astimezone(self.timezone)
            end = _aware(
                datetime.fromisoformat(str(task.get("scheduled_end")))
            ).astimezone(self.timezone)
        except ValueError:
            return None
        return (start, end) if end > start else None

    @staticmethod
    def _priority(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 99

    @staticmethod
    def _minutes(value: Any) -> int:
        try:
            minutes = int(value)
        except (TypeError, ValueError):
            minutes = 30
        return min(max(minutes, MIN_SLOT_MINUTES), 8 * 60)

    @staticmethod
    def _interval_is_free(
        interval: tuple[datetime, datetime], free: list[tuple[datetime, datetime]]
    ) -> bool:
        return any(interval[0] >= start and interval[1] <= end for start, end in free)

    @staticmethod
    def _reserve(
        free: list[tuple[datetime, datetime]], interval: tuple[datetime, datetime]
    ) -> list[tuple[datetime, datetime]]:
        result = []
        for start, end in free:
            if interval[1] <= start or interval[0] >= end:
                result.append((start, end))
            else:
                if interval[0] > start:
                    result.append((start, interval[0]))
                if interval[1] < end:
                    result.append((interval[1], end))
        return result

    @staticmethod
    def _allocate(
        free: list[tuple[datetime, datetime]], minutes: int
    ) -> tuple[tuple[datetime, datetime] | None, bool]:
        duration = timedelta(minutes=minutes)
        for start, end in free:
            if end - start >= duration:
                return (start, start + duration), False
        available = [
            (end - start, start, end)
            for start, end in free
            if end - start >= timedelta(minutes=MIN_SLOT_MINUTES)
        ]
        if not available:
            return None, False
        _duration, start, end = max(available, key=lambda item: item[0])
        return (start, end), True
