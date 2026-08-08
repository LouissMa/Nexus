from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_ID = r"(?P<item_id>[A-Za-z0-9_-]{1,100})"


class DashboardActions:
    """Allowlisted Dashboard mutations backed by Nexus domain services."""

    def __init__(
        self,
        service: Any,
        *,
        timezone: str = "UTC",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.service = service
        try:
            self.timezone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be an IANA timezone name.") from exc
        self.clock = clock or (lambda: datetime.now(UTC))
        self._routes = (
            (re.compile(rf"^/api/habits/{_ID}/check-in$"), self._check_in_habit),
            (
                re.compile(rf"^/api/projects/{_ID}/progress$"),
                self._update_project_progress,
            ),
            (re.compile(rf"^/api/suggestions/{_ID}/accept$"), self._accept_suggestion),
            (
                re.compile(rf"^/api/suggestions/{_ID}/dismiss$"),
                self._dismiss_suggestion,
            ),
            (re.compile(r"^/api/replan/preview$"), self._preview_replan),
            (re.compile(r"^/api/replan/apply$"), self._apply_replan),
        )

    def dispatch(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        for pattern, handler in self._routes:
            match = pattern.fullmatch(path)
            if match:
                return handler(match.groupdict().get("item_id"), payload)
        return None

    def _check_in_habit(
        self, habit_id: str | None, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self._schema(payload, required=(), optional=("date", "count", "note"))
        local_date = (
            payload.get("date")
            or self.clock().astimezone(self.timezone).date().isoformat()
        )
        count = payload.get("count", 1)
        note = payload.get("note", "Dashboard check-in")
        if not isinstance(local_date, str) or not isinstance(note, str):
            raise ValueError("date and note must be strings.")
        return self.service.check_in_habit(
            habit_id,
            local_date,
            count,
            note,
            timezone=str(self.timezone),
            now=self.clock(),
        )

    def _update_project_progress(
        self, project_id: str | None, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self._schema(payload, required=("percent",), optional=("note", "correction"))
        note = payload.get("note", "Dashboard update")
        correction = payload.get("correction", False)
        if not isinstance(note, str) or not isinstance(correction, bool):
            raise ValueError("note must be a string and correction must be boolean.")
        return self.service.update_project_progress(
            project_id, payload["percent"], note, correction, now=self.clock()
        )

    def _accept_suggestion(
        self, suggestion_id: str | None, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self._schema(payload, required=(), optional=())
        return self.service.accept_suggestion(
            suggestion_id, approved=True, timezone=str(self.timezone), now=self.clock()
        )

    def _dismiss_suggestion(
        self, suggestion_id: str | None, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self._schema(payload, required=(), optional=())
        return self.service.dismiss_suggestion(
            suggestion_id, timezone=str(self.timezone), now=self.clock()
        )

    def _preview_replan(
        self, _item_id: str | None, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self._schema(
            payload,
            required=("date",),
            optional=("events", "working_start", "working_end", "calendar_unavailable"),
        )
        events = (
            None if payload.get("calendar_unavailable") else payload.get("events", [])
        )
        return self.service.preview_replan(
            payload["date"],
            events,
            (
                payload.get("working_start", "09:00"),
                payload.get("working_end", "18:00"),
            ),
            timezone=str(self.timezone),
            now=self.clock(),
        )

    def _apply_replan(
        self, _item_id: str | None, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self._schema(
            payload, required=("preview",), optional=("events", "calendar_unavailable")
        )
        events = (
            None if payload.get("calendar_unavailable") else payload.get("events", [])
        )
        return self.service.apply_replan(
            payload["preview"], events, timezone=str(self.timezone), now=self.clock()
        )

    @staticmethod
    def _schema(
        payload: dict[str, Any], *, required: tuple[str, ...], optional: tuple[str, ...]
    ) -> None:
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object.")
        allowed = set(required).union(optional)
        if set(payload) - allowed or any(key not in payload for key in required):
            raise ValueError("JSON body does not match the endpoint schema.")
