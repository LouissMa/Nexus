from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .habits import habit_summary
from .store import JsonStore

ALLOWED_ACTIONS = {"acknowledge", "schedule_goal_step", "start_task"}
MAX_SUGGESTIONS = 100
MAX_RESULTS = 20


class SuggestionWordingAdapter:
    """Allow an LLM to rewrite wording without changing suggestion decisions."""

    @staticmethod
    def rewrite(items: list[dict[str, Any]], llm: Any) -> list[dict[str, Any]]:
        public = [
            {"id": item["id"], "title": item["title"], "reason": item["reason"]}
            for item in items
        ]
        response = llm.generate(
            "Rewrite suggestion wording. Return only a JSON array with id, title, and reason. Preserve every id and do not add fields.",
            json.dumps(public, ensure_ascii=False),
        )
        try:
            rewritten = json.loads(response)
        except json.JSONDecodeError as exc:
            raise ValueError("LLM suggestion wording must be valid JSON.") from exc
        if not isinstance(rewritten, list):
            raise ValueError("LLM suggestion wording must be a JSON array.")
        by_id: dict[str, dict[str, str]] = {}
        for item in rewritten:
            if not isinstance(item, dict) or set(item) != {"id", "title", "reason"}:
                raise ValueError("LLM suggestion wording used an invalid schema.")
            if not all(
                isinstance(item.get(key), str) for key in ("id", "title", "reason")
            ):
                raise ValueError("LLM suggestion wording fields must be strings.")
            by_id[item["id"]] = item
        if set(by_id) != {item["id"] for item in items}:
            raise ValueError(
                "LLM suggestion wording must preserve every suggestion id."
            )
        result = deepcopy(items)
        for item in result:
            replacement = by_id[item["id"]]
            item["title"] = replacement["title"].strip()[:300] or item["title"]
            item["reason"] = replacement["reason"].strip()[:1_000] or item["reason"]
        return result


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _timestamp(value: datetime) -> str:
    return _aware(value).astimezone(UTC).replace(microsecond=0).isoformat()


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return _aware(datetime.fromisoformat(value))
    except ValueError:
        return None


def _stable_id(kind: str, source_ids: list[str]) -> str:
    payload = "|".join((kind, *sorted(source_ids))).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


class SuggestionEngine:
    def __init__(self, *, timezone: str = "UTC") -> None:
        try:
            self.timezone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be an IANA timezone name.") from exc

    def generate(
        self,
        state: dict[str, Any],
        now: datetime,
        calendar: list[dict[str, Any]] | None = None,
        memories: list[dict[str, Any]] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= MAX_RESULTS
        ):
            raise ValueError(f"limit must be an integer from 1 to {MAX_RESULTS}.")
        current = _aware(now)
        today = current.astimezone(self.timezone).date()
        candidates: list[tuple[int, dict[str, Any]]] = []
        self._task_candidates(state, current, today, candidates)
        self._goal_candidates(state, current, candidates)
        self._habit_candidates(state, current, today, candidates)
        self._milestone_candidates(state, current, today, candidates)
        self._calendar_candidates(state, current, today, calendar or [], candidates)
        self._memory_candidates(current, memories or [], candidates)
        candidates.sort(key=lambda item: (-item[0], item[1]["id"]))
        return [item for _, item in candidates[:limit]]

    def _calendar_candidates(
        self,
        state: dict[str, Any],
        now: datetime,
        today: date,
        calendar: list[dict[str, Any]],
        candidates: list[tuple[int, dict[str, Any]]],
    ) -> None:
        day_start = datetime.combine(today, time(9), self.timezone)
        day_end = datetime.combine(today, time(18), self.timezone)
        events: list[tuple[datetime, datetime, str, str]] = []
        for raw in calendar[:100] if isinstance(calendar, list) else []:
            if not isinstance(raw, dict):
                continue
            try:
                start = _aware(
                    datetime.fromisoformat(str(raw.get("start")))
                ).astimezone(self.timezone)
                end = _aware(datetime.fromisoformat(str(raw.get("end")))).astimezone(
                    self.timezone
                )
            except ValueError:
                continue
            if raw.get("all_day") and start.date() <= today < end.date():
                start, end = day_start, day_end
            clipped = (max(start, day_start), min(end, day_end))
            if clipped[1] <= clipped[0]:
                continue
            title = str(raw.get("summary") or "calendar event")[:300]
            source = self._calendar_source(raw)
            events.append((clipped[0], clipped[1], title, source))
        events.sort(key=lambda item: (item[0], item[1], item[3]))
        if not events:
            return

        for task in state.get("daily_tasks", []):
            if not isinstance(task, dict) or task.get("status") == "completed":
                continue
            try:
                task_start = _aware(
                    datetime.fromisoformat(str(task.get("scheduled_start")))
                ).astimezone(self.timezone)
                task_end = _aware(
                    datetime.fromisoformat(str(task.get("scheduled_end")))
                ).astimezone(self.timezone)
            except ValueError:
                continue
            for event_start, event_end, event_title, event_source in events:
                if task_start < event_end and task_end > event_start and task.get("id"):
                    task_id = str(task["id"])
                    candidates.append(
                        (
                            95,
                            self._item(
                                "calendar_conflict",
                                f"Replan {task.get('title') or 'scheduled task'}",
                                f"This task overlaps the calendar event '{event_title}'.",
                                {"type": "acknowledge"},
                                0.92,
                                [f"task:{task_id}", event_source],
                                now,
                            ),
                        )
                    )
                    break

        merged: list[list[datetime]] = []
        for start, end, _title, _source in events:
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        windows: list[tuple[datetime, datetime]] = []
        cursor = day_start
        for start, end in merged:
            if start > cursor:
                windows.append((cursor, start))
            cursor = max(cursor, end)
        if cursor < day_end:
            windows.append((cursor, day_end))
        windows = [
            window
            for window in windows
            if (window[1] - window[0]).total_seconds() >= 30 * 60
        ]
        if windows:
            start, end = max(windows, key=lambda item: item[1] - item[0])
            source = f"calendar:{hashlib.sha256(f'{today}|{start.isoformat()}|{end.isoformat()}'.encode()).hexdigest()[:12]}"
            candidates.append(
                (
                    55,
                    self._item(
                        "calendar_focus_window",
                        f"Use the {start:%H:%M}-{end:%H:%M} focus window",
                        "Your calendar leaves this as today's longest working-hours focus window.",
                        {"type": "acknowledge"},
                        0.78,
                        [source],
                        now,
                    ),
                )
            )

    def _memory_candidates(
        self,
        now: datetime,
        memories: list[dict[str, Any]],
        candidates: list[tuple[int, dict[str, Any]]],
    ) -> None:
        for memory in memories[:3] if isinstance(memories, list) else []:
            if not isinstance(memory, dict) or not memory.get("id"):
                continue
            text = str(memory.get("text") or "").strip()
            if not text:
                continue
            try:
                score = float(memory.get("retrieval_score", 0.5))
            except (TypeError, ValueError):
                score = 0.5
            score = max(0.0, min(1.0, score))
            memory_id = str(memory["id"])[:100]
            candidates.append(
                (
                    50 + round(score * 20),
                    self._item(
                        "relevant_memory",
                        "Reconnect a relevant memory",
                        f"Relevant context from long-term memory: {text[:500]}",
                        {"type": "acknowledge"},
                        0.6 + score * 0.3,
                        [f"memory:{memory_id}"],
                        now,
                    ),
                )
            )

    @staticmethod
    def _calendar_source(event: dict[str, Any]) -> str:
        payload = "|".join(
            str(event.get(field) or "") for field in ("summary", "start", "end")
        )
        return f"calendar:{hashlib.sha256(payload.encode()).hexdigest()[:12]}"

    def _task_candidates(
        self,
        state: dict[str, Any],
        now: datetime,
        today: date,
        candidates: list[tuple[int, dict[str, Any]]],
    ) -> None:
        for task in state.get("daily_tasks", []):
            if (
                not isinstance(task, dict)
                or task.get("status") == "completed"
                or not task.get("id")
            ):
                continue
            task_id = str(task["id"])
            if task.get("status") == "blocked" or task.get("blocker"):
                reason = f"This task is blocked: {task.get('blocker') or 'no blocker reason was recorded'}."
                candidates.append(
                    (
                        100,
                        self._item(
                            "blocked_task",
                            f"Unblock {task.get('title') or 'task'}",
                            reason,
                            {"type": "acknowledge"},
                            0.95,
                            [f"task:{task_id}"],
                            now,
                        ),
                    )
                )
            elif (
                task.get("status") == "pending"
                and task.get("plan_date") == today.isoformat()
            ):
                candidates.append(
                    (
                        60 - int(task.get("priority", 3)),
                        self._item(
                            "pending_task",
                            f"Start {task.get('title') or 'today task'}",
                            "This planned task is still pending today.",
                            {"type": "start_task", "task_id": task_id},
                            0.75,
                            [f"task:{task_id}"],
                            now,
                        ),
                    )
                )

    def _goal_candidates(
        self,
        state: dict[str, Any],
        now: datetime,
        candidates: list[tuple[int, dict[str, Any]]],
    ) -> None:
        for goal in state.get("goals", []):
            if (
                not isinstance(goal, dict)
                or goal.get("status", "active") != "active"
                or not goal.get("id")
            ):
                continue
            reference = _parse_timestamp(goal.get("last_check_in")) or _parse_timestamp(
                goal.get("created_at")
            )
            cadence = max(1, int(goal.get("cadence_days", 3)))
            if reference is None:
                continue
            quiet_days = max(0, (now - reference).days)
            if quiet_days >= cadence:
                goal_id = str(goal["id"])
                candidates.append(
                    (
                        80 + min(quiet_days, 10),
                        self._item(
                            "quiet_goal",
                            f"Move {goal.get('title') or 'goal'} forward",
                            f"This goal has had no check-in for {quiet_days} days; its cadence is {cadence} days.",
                            {"type": "schedule_goal_step", "goal_id": goal_id},
                            min(0.95, 0.7 + quiet_days / 100),
                            [f"goal:{goal_id}"],
                            now,
                        ),
                    )
                )

    def _habit_candidates(
        self,
        state: dict[str, Any],
        now: datetime,
        today: date,
        candidates: list[tuple[int, dict[str, Any]]],
    ) -> None:
        for habit in state.get("habits", []):
            if (
                not isinstance(habit, dict)
                or habit.get("status") != "active"
                or not habit.get("id")
            ):
                continue
            summary = habit_summary(habit, today)
            if summary["due_today"] and not summary["today_complete"]:
                habit_id = str(habit["id"])
                candidates.append(
                    (
                        70 + min(summary["streak"], 5),
                        self._item(
                            "habit_risk",
                            f"Protect {habit.get('name') or 'habit'}",
                            f"This habit is due today and has {summary['today_count']} of {habit.get('target_count', 1)} required check-ins.",
                            {"type": "acknowledge"},
                            0.8,
                            [f"habit:{habit_id}"],
                            now,
                        ),
                    )
                )

    def _milestone_candidates(
        self,
        state: dict[str, Any],
        now: datetime,
        today: date,
        candidates: list[tuple[int, dict[str, Any]]],
    ) -> None:
        for project in state.get("projects", []):
            if not isinstance(project, dict) or project.get("status") != "active":
                continue
            for milestone in project.get("milestones", []):
                if (
                    not isinstance(milestone, dict)
                    or milestone.get("status") == "completed"
                ):
                    continue
                try:
                    target = date.fromisoformat(str(milestone.get("target_date")))
                except ValueError:
                    continue
                days = (target - today).days
                if days <= 7 and milestone.get("id") and project.get("id"):
                    timing = (
                        f"due in {days} days"
                        if days >= 0
                        else f"overdue by {-days} days"
                    )
                    sources = [
                        f"project:{project['id']}",
                        f"milestone:{milestone['id']}",
                    ]
                    candidates.append(
                        (
                            90 + max(0, -days),
                            self._item(
                                "milestone_deadline",
                                f"Finish {milestone.get('title') or 'milestone'}",
                                f"The {project.get('name') or 'project'} milestone is {timing}.",
                                {"type": "acknowledge"},
                                0.9,
                                sources,
                                now,
                            ),
                        )
                    )

    @staticmethod
    def _item(
        kind: str,
        title: str,
        reason: str,
        action: dict[str, Any],
        confidence: float,
        source_ids: list[str],
        now: datetime,
    ) -> dict[str, Any]:
        return {
            "id": _stable_id(kind, source_ids),
            "kind": kind,
            "title": str(title)[:300],
            "reason": str(reason)[:1_000],
            "action": deepcopy(action),
            "confidence": round(max(0.0, min(1.0, confidence)), 4),
            "source_ids": source_ids[:20],
            "source_types": sorted(
                {source.split(":", 1)[0] for source in source_ids if ":" in source}
            )[:10],
            "created_at": _timestamp(now),
            "expires_at": _timestamp(now + timedelta(days=2)),
            "status": "open",
        }


class SuggestionService:
    def __init__(self, store: JsonStore, *, timezone: str = "UTC") -> None:
        self.store = store
        self.engine = SuggestionEngine(timezone=timezone)
        self.timezone = self.engine.timezone

    def list(
        self,
        *,
        now: datetime | None = None,
        refresh: bool = False,
        limit: int = 10,
        calendar: list[dict[str, Any]] | None = None,
        memories: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        current = _aware(now or datetime.now(UTC))
        if refresh:
            safe_context = self._context(context)
            generated = self.engine.generate(
                self.store.load(),
                current,
                calendar=calendar,
                memories=memories,
                limit=limit,
            )
            for item in generated:
                item["context"] = deepcopy(safe_context)

            def mutation(state: dict[str, Any]) -> list[dict[str, Any]]:
                existing = {
                    item.get("id"): item
                    for item in state.setdefault("suggestions", [])
                    if isinstance(item, dict)
                }
                for item in generated:
                    previous = existing.get(item["id"])
                    if previous and previous.get("status") in {"accepted", "dismissed"}:
                        item["status"] = previous["status"]
                        for field in ("accepted_at", "dismissed_at"):
                            if previous.get(field):
                                item[field] = previous[field]
                state["suggestions"] = deepcopy(generated[-MAX_SUGGESTIONS:])
                state["suggestion_context"] = deepcopy(safe_context)
                return deepcopy(state["suggestions"])

            suggestions = self.store.mutate(mutation)
        else:
            suggestions = deepcopy(self.store.load().get("suggestions", []))
        return [
            item
            for item in suggestions
            if isinstance(item, dict)
            and (_parse_timestamp(item.get("expires_at")) or current) > current
        ][:limit]

    def context(self) -> dict[str, Any]:
        return self._context(self.store.load().get("suggestion_context"))

    @staticmethod
    def _context(value: dict[str, Any] | None) -> dict[str, Any]:
        raw = value if isinstance(value, dict) else {}
        allowed = {"available", "unavailable", "not_requested"}
        calendar = str(raw.get("calendar", "not_requested"))
        rag = str(raw.get("rag", "unavailable"))
        degradations = raw.get("degradations", [])
        return {
            "calendar": calendar if calendar in allowed else "unavailable",
            "rag": rag if rag in allowed else "unavailable",
            "degradations": [
                str(item)[:100]
                for item in (degradations if isinstance(degradations, list) else [])[
                    :10
                ]
            ],
        }

    def accept(
        self, suggestion_id: str, *, approved: bool, now: datetime | None = None
    ) -> dict[str, Any]:
        if not approved:
            raise ValueError("Explicit approval is required to accept a suggestion.")
        current = _aware(now or datetime.now(UTC))

        def mutation(state: dict[str, Any]) -> dict[str, Any]:
            suggestion = self._find(state, suggestion_id, current)
            action = (
                suggestion.get("action")
                if isinstance(suggestion.get("action"), dict)
                else {}
            )
            action_type = action.get("type")
            if action_type not in ALLOWED_ACTIONS:
                raise ValueError(f"Suggestion action '{action_type}' is not allowed.")
            action_result = self._apply_action(state, suggestion, action, current)
            suggestion["status"] = "accepted"
            suggestion["accepted_at"] = _timestamp(current)
            return {"suggestion": deepcopy(suggestion), "action_result": action_result}

        return self.store.mutate(mutation)

    def dismiss(
        self, suggestion_id: str, *, now: datetime | None = None
    ) -> dict[str, Any]:
        current = _aware(now or datetime.now(UTC))

        def mutation(state: dict[str, Any]) -> dict[str, Any]:
            suggestion = self._find(state, suggestion_id, current)
            suggestion["status"] = "dismissed"
            suggestion["dismissed_at"] = _timestamp(current)
            return deepcopy(suggestion)

        return self.store.mutate(mutation)

    def _apply_action(
        self,
        state: dict[str, Any],
        suggestion: dict[str, Any],
        action: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any]:
        if action["type"] == "acknowledge":
            return {"acknowledged": True}
        if action["type"] == "start_task":
            for task in state.setdefault("daily_tasks", []):
                if task.get("id") == action.get("task_id"):
                    if task.get("status") == "pending":
                        task["status"] = "in_progress"
                        task["updated_at"] = _timestamp(now)
                    return {"task": deepcopy(task)}
            raise ValueError(f"Task '{action.get('task_id')}' not found.")
        goal_id = action.get("goal_id")
        goal = next(
            (
                item
                for item in state.setdefault("goals", [])
                if item.get("id") == goal_id
                and item.get("status", "active") == "active"
            ),
            None,
        )
        if goal is None:
            raise ValueError(f"Goal '{goal_id}' not found.")
        existing = next(
            (
                item
                for item in state.setdefault("daily_tasks", [])
                if item.get("source_suggestion_id") == suggestion["id"]
            ),
            None,
        )
        if existing is not None:
            return {"task": deepcopy(existing), "created": False}
        task = {
            "id": hashlib.sha256(f"task|{suggestion['id']}".encode()).hexdigest()[:8],
            "plan_date": now.astimezone(self.timezone).date().isoformat(),
            "goal_id": goal_id,
            "goal_title": goal.get("title", "Goal"),
            "title": f"Advance '{goal.get('title', 'goal')}' and record one result",
            "priority": 1,
            "estimated_minutes": 30,
            "status": "pending",
            "blocker": None,
            "unresolved": [],
            "notes": [],
            "source_suggestion_id": suggestion["id"],
            "created_at": _timestamp(now),
            "updated_at": None,
        }
        state["daily_tasks"].append(task)
        return {"task": deepcopy(task), "created": True}

    @staticmethod
    def _find(
        state: dict[str, Any], suggestion_id: str, now: datetime
    ) -> dict[str, Any]:
        for suggestion in state.setdefault("suggestions", []):
            if suggestion.get("id") != suggestion_id:
                continue
            expires = _parse_timestamp(suggestion.get("expires_at"))
            if expires is None or expires <= now:
                raise ValueError(f"Suggestion '{suggestion_id}' is expired.")
            return suggestion
        raise ValueError(f"Suggestion '{suggestion_id}' not found.")
