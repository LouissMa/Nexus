from __future__ import annotations

import ipaddress
import json
import re
import secrets
import socket
import threading
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from itertools import islice
from typing import Any, Protocol
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .dashboard_actions import DashboardActions
from .habits import habit_summary
from .memory_lifecycle import is_memory_eligible, normalize_memory
from .projects import project_summary


class RecentStore(Protocol):
    def recent(self, limit: int = 50) -> list[dict[str, Any]]: ...


StateSource = Callable[[], Mapping[str, Any]]
MappingSource = Callable[[], Mapping[str, Any]]

_SECTION_NAMES = (
    "today",
    "goals",
    "habits",
    "projects",
    "suggestions",
    "memory",
    "activity",
    "settings",
)
_SECRET_VALUE = "[redacted]"
_MAX_STRING_CHARS = 1_000
_MAX_LIST_ITEMS = 100
_MAX_DICT_ITEMS = 100
_MAX_DEPTH = 6
_MAX_STATE_SCAN = 500
_SENSITIVE_KEYS = {
    "apikey",
    "accesskey",
    "authorization",
    "bearer",
    "credential",
    "credentials",
    "key",
    "password",
    "privatekey",
    "secret",
    "secretkey",
    "signingkey",
    "token",
    "webhook",
    "webhookurl",
}
_OMITTED_KEYS = {
    "arguments",
    "argv",
    "command",
    "content",
    "cwd",
    "env",
    "headers",
    "output",
    "path",
    "prompt",
    "raw",
    "rawcontent",
    "reportpath",
    "stderr",
    "stdin",
    "stdout",
    "systemprompt",
    "userprompt",
}
_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_KEY_PATTERN = re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{8,}", re.IGNORECASE)
_BEARER_PATTERN = re.compile(r"\bBearer\s+[^\s,;]+", re.IGNORECASE)
_ASSIGNMENT_PATTERN = re.compile(
    r"\b(?:api[\s_-]?key|access[\s_-]?key|password|secret|token|key)"
    r"\s*[:=]\s*[^\s,;]+",
    re.IGNORECASE,
)

_PROFILE_FIELDS = ("display_name", "timezone")
_RUNTIME_FIELDS = (
    "enabled_jobs",
    "morning_time",
    "evening_time",
    "reminder_time",
    "grace_minutes",
    "poll_interval_seconds",
    "quiet_hours_start",
    "quiet_hours_end",
    "inbox_enabled",
    "console_enabled",
    "use_llm",
    "live_tools",
    "agents",
    "coach_mode",
)
_LLM_FIELDS = (
    "provider",
    "simple_model",
    "complex_model",
    "default_tier",
    "timeout_seconds",
    "is_configured",
)
_EMBEDDING_FIELDS = (
    "provider",
    "model",
    "collection_name",
    "timeout_seconds",
    "semantic_enabled",
    "is_configured",
)
_TOOL_FIELDS = ("enabled", "allowed_operations", "location", "repo")
_MCP_FIELDS = ("enabled", "transport", "policy", "tool_policies")
_AUTOMATION_FIELDS = ("enabled", "type", "policy", "timeout_seconds")


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(microsecond=0).isoformat()


def _bounded_text(value: str) -> str:
    if len(value) <= _MAX_STRING_CHARS:
        return value
    return value[: _MAX_STRING_CHARS - 3] + "..."


def _sanitize_text(value: str) -> str:
    sanitized = _bounded_text(value)
    sanitized = _URL_PATTERN.sub("[redacted-url]", sanitized)
    sanitized = _KEY_PATTERN.sub("[redacted-key]", sanitized)
    sanitized = _BEARER_PATTERN.sub("Bearer [redacted]", sanitized)
    return _ASSIGNMENT_PATTERN.sub("credential=[redacted]", sanitized)


def _sanitize_mapping(value: Any, key: str = "", depth: int = 0) -> Any:
    if depth >= _MAX_DEPTH:
        return "[truncated]"
    normalized_key = _normalized_key(key)
    if normalized_key in _OMITTED_KEYS:
        return None
    if normalized_key in _SENSITIVE_KEYS or normalized_key.endswith("apikey"):
        if value in (None, "", False):
            return value
        return _SECRET_VALUE
    if normalized_key.endswith("url"):
        return _SECRET_VALUE if value else value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for item_key, item_value in islice(value.items(), _MAX_DICT_ITEMS):
            public_key = _bounded_text(str(item_key))
            if _normalized_key(public_key) in _OMITTED_KEYS:
                continue
            result[public_key] = _sanitize_mapping(item_value, public_key, depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [
            _sanitize_mapping(item, depth=depth + 1) for item in value[:_MAX_LIST_ITEMS]
        ]
    if isinstance(value, str):
        return _sanitize_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _sanitize_text(str(value))


def _public_record(record: Any, fields: tuple[str, ...]) -> dict[str, Any] | None:
    if not isinstance(record, Mapping):
        return None
    public: dict[str, Any] = {}
    for field in fields:
        if field not in record:
            continue
        value = _sanitize_mapping(record[field], field)
        if value is not None:
            public[field] = value
    return public


def _bounded_records(value: Any, limit: int) -> list[Any]:
    if not isinstance(value, (list, tuple)):
        return []
    return list(value[:limit])


def _has_configured_secret(value: Mapping[str, Any]) -> bool:
    for key, item in islice(value.items(), _MAX_DICT_ITEMS):
        normalized = _normalized_key(str(key))
        if (
            normalized in _SENSITIVE_KEYS
            or normalized.endswith("apikey")
            or normalized in _OMITTED_KEYS
        ) and item not in (None, "", False, [], {}):
            return True
    return False


def _allowlisted_fields(
    value: Any,
    fields: tuple[str, ...],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    public: dict[str, Any] = {}
    for field in fields:
        if field in value:
            item = _sanitize_mapping(value[field], field)
            if item is not None:
                public[field] = item
    return public


def _allowlisted_named_settings(
    value: Any,
    fields: tuple[str, ...],
    *,
    configured_label: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        return {}
    public: dict[str, dict[str, Any]] = {}
    for raw_name, raw_settings in islice(value.items(), _MAX_DICT_ITEMS):
        if not isinstance(raw_settings, Mapping):
            continue
        name = _sanitize_text(str(raw_name))
        summary = _allowlisted_fields(raw_settings, fields)
        if _has_configured_secret(raw_settings):
            summary[configured_label] = True
        public[name] = summary
    return public


def _public_settings(settings: Mapping[str, Any]) -> dict[str, Any]:
    public: dict[str, Any] = {}
    if "profile" in settings:
        public["profile"] = _allowlisted_fields(settings["profile"], _PROFILE_FIELDS)
    if "runtime" in settings:
        runtime = _allowlisted_fields(settings["runtime"], _RUNTIME_FIELDS)
        raw_runtime = settings["runtime"]
        if isinstance(raw_runtime, Mapping) and raw_runtime.get("webhook_url"):
            runtime["webhook_configured"] = True
        public["runtime"] = runtime
    if "llm" in settings:
        llm = _allowlisted_fields(settings["llm"], _LLM_FIELDS)
        if isinstance(settings["llm"], Mapping) and _has_configured_secret(
            settings["llm"]
        ):
            llm["credentials_configured"] = True
        public["llm"] = llm
    if "embedding" in settings:
        embedding = _allowlisted_fields(settings["embedding"], _EMBEDDING_FIELDS)
        if isinstance(settings["embedding"], Mapping) and _has_configured_secret(
            settings["embedding"]
        ):
            embedding["credentials_configured"] = True
        public["embedding"] = embedding
    if "tools" in settings:
        public["tools"] = _allowlisted_named_settings(
            settings["tools"],
            _TOOL_FIELDS,
            configured_label="credentials_configured",
        )
    if "mcp" in settings:
        raw_mcp = settings["mcp"]
        if isinstance(raw_mcp, Mapping) and isinstance(raw_mcp.get("servers"), Mapping):
            raw_mcp = raw_mcp["servers"]
        public["mcp"] = _allowlisted_named_settings(
            raw_mcp,
            _MCP_FIELDS,
            configured_label="connection_configured",
        )
    if "automations" in settings:
        raw_automations = settings["automations"]
        if isinstance(raw_automations, Mapping) and isinstance(
            raw_automations.get("definitions"), Mapping
        ):
            raw_automations = raw_automations["definitions"]
        public["automations"] = _allowlisted_named_settings(
            raw_automations,
            _AUTOMATION_FIELDS,
            configured_label="target_configured",
        )
    return public


def _bounded_memory_strings(
    value: Any,
    *,
    limit: int,
    max_chars: int,
) -> list[str]:
    if not isinstance(value, (list, tuple)):
        raise TypeError("memory collection must be a list or tuple")
    sliced = value[:limit]
    if not isinstance(sliced, (list, tuple)):
        raise TypeError("memory collection slice must be a list or tuple")
    bounded: list[str] = []
    for item in sliced:
        if not isinstance(item, str):
            raise TypeError("memory collection values must be strings")
        bounded.append(item[:max_chars])
    return bounded


def _bounded_raw_memory(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    memory_id = raw.get("id")
    text = raw.get("text")
    if not isinstance(memory_id, str) or not isinstance(text, str):
        return None
    bounded_id = memory_id[:256]
    bounded_text_prefix = text[:_MAX_STRING_CHARS]
    if not bounded_id.strip() or not bounded_text_prefix.strip():
        return None
    bounded_text = _bounded_text(text)

    bounded: dict[str, Any] = {
        "id": bounded_id,
        "text": bounded_text,
        "tags": _bounded_memory_strings(
            raw.get("tags", []),
            limit=_MAX_LIST_ITEMS,
            max_chars=200,
        ),
    }
    nullable_strings = (
        "created_at",
        "updated_at",
        "privacy",
        "status",
        "importance_source",
        "expires_at",
        "duplicate_of",
        "supersedes",
        "archived_at",
        "forgotten_at",
    )
    for field in nullable_strings:
        if field not in raw:
            continue
        value = raw[field]
        if value is None:
            bounded[field] = None
        elif isinstance(value, str):
            bounded[field] = value[:256]
        else:
            return None

    if "importance" in raw:
        importance = raw["importance"]
        if isinstance(importance, bool) or not isinstance(importance, (int, float)):
            return None
        bounded["importance"] = importance
    if "pinned" in raw:
        if not isinstance(raw["pinned"], bool):
            return None
        bounded["pinned"] = raw["pinned"]

    for field in ("conflicts_with", "summary_of"):
        if field in raw:
            bounded[field] = _bounded_memory_strings(
                raw[field],
                limit=_MAX_LIST_ITEMS,
                max_chars=256,
            )
    return bounded


class DashboardSnapshot:
    """Build a bounded, privacy-filtered view of Nexus runtime state."""

    MAX_SECTION_ITEMS = _MAX_LIST_ITEMS

    def __init__(
        self,
        *,
        state_source: StateSource,
        notifications: RecentStore | None = None,
        tool_audit: RecentStore | None = None,
        mcp_audit: RecentStore | None = None,
        agent_traces: RecentStore | None = None,
        automation_audit: RecentStore | None = None,
        scheduler_status: MappingSource | None = None,
        settings: MappingSource | None = None,
        clock: Callable[[], datetime] | None = None,
        recent_limit: int = 30,
        memory_privacy: str = "private",
        timezone: str = "UTC",
    ) -> None:
        if recent_limit < 1 or recent_limit > 200:
            raise ValueError("recent_limit must be between 1 and 200.")
        if not isinstance(timezone, str):
            raise ValueError("timezone must be an IANA timezone name.")
        try:
            self._timezone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be an IANA timezone name.") from error
        self._state_source = state_source
        self._notifications = notifications
        self._tool_audit = tool_audit
        self._mcp_audit = mcp_audit
        self._agent_traces = agent_traces
        self._automation_audit = automation_audit
        self._scheduler_status = scheduler_status
        self._settings = settings
        self._clock = clock or (lambda: datetime.now(UTC))
        self._recent_limit = recent_limit
        self._memory_privacy = memory_privacy

    def build(self) -> dict[str, Any]:
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        builders: dict[str, Callable[[], dict[str, Any]]] = {
            "today": lambda: self._build_today(now),
            "goals": self._build_goals,
            "habits": lambda: self._build_habits(now),
            "projects": self._build_projects,
            "suggestions": lambda: self._build_suggestions(now),
            "memory": lambda: self._build_memory(now),
            "activity": self._build_activity,
            "settings": self._build_settings,
        }
        sections: dict[str, dict[str, Any]] = {}
        for name in _SECTION_NAMES:
            try:
                data = builders[name]()
            except Exception:
                sections[name] = {
                    "status": "error",
                    "data": None,
                    "error": f"{name}_unavailable",
                }
            else:
                sections[name] = {"status": "ok", "data": data, "error": None}
        return {"generated_at": _utc_iso(now), "sections": sections}

    def _state(self) -> Mapping[str, Any]:
        state = self._state_source()
        if not isinstance(state, Mapping):
            raise TypeError("Dashboard state source must return a mapping.")
        return state

    def _recent(self, source: RecentStore | None) -> list[dict[str, Any]]:
        if source is None:
            return []
        records = source.recent(limit=self._recent_limit)
        if not isinstance(records, (list, tuple)):
            raise TypeError("Dashboard recent source must return a list.")
        bounded = records[-self._recent_limit :]
        return [record for record in bounded if isinstance(record, dict)]

    def _build_today(self, now: datetime) -> dict[str, Any]:
        state = self._state()
        today = now.astimezone(self._timezone).date().isoformat()
        tasks = []
        for task in _bounded_records(state.get("daily_tasks", []), _MAX_STATE_SCAN):
            if not isinstance(task, Mapping) or task.get("plan_date") != today:
                continue
            public = _public_record(
                task,
                (
                    "id",
                    "plan_date",
                    "title",
                    "goal_id",
                    "goal_title",
                    "status",
                    "priority",
                    "estimated_minutes",
                    "blocker",
                    "unresolved",
                    "notes",
                    "updated_at",
                ),
            )
            if public is not None:
                tasks.append(public)
            if len(tasks) >= self.MAX_SECTION_ITEMS:
                break
        tasks.sort(key=lambda item: (item.get("priority", 99), item.get("title", "")))

        notifications = []
        for record in self._recent(self._notifications):
            public = _public_record(
                record,
                (
                    "id",
                    "kind",
                    "title",
                    "body",
                    "created_at",
                    "urgency",
                    "status",
                    "delivery",
                ),
            )
            if public is not None:
                notifications.append(public)

        scheduler = self._scheduler_status() if self._scheduler_status else {}
        if not isinstance(scheduler, Mapping):
            raise TypeError("Scheduler status source must return a mapping.")
        scheduled_jobs = self._scheduled_jobs(scheduler)
        latest_briefing = self._latest_notification(
            notifications, {"morning_briefing", "briefing"}
        )
        latest_review = self._latest_notification(
            notifications, {"evening_review", "review"}
        )
        reminders = [
            item
            for item in notifications
            if item.get("kind") in {"stale_goal_reminders", "reminder"}
        ][-self._recent_limit :]
        return {
            "date": today,
            "timezone": str(self._timezone),
            "tasks": tasks,
            "notifications": notifications,
            "scheduled_jobs": scheduled_jobs,
            "reminders": reminders,
            "latest_briefing": latest_briefing,
            "latest_review": latest_review,
            "scheduler": self._public_scheduler(scheduler, scheduled_jobs),
        }

    @staticmethod
    def _latest_notification(
        notifications: list[dict[str, Any]], kinds: set[str]
    ) -> dict[str, Any] | None:
        return next(
            (
                notification
                for notification in reversed(notifications)
                if notification.get("kind") in kinds
            ),
            None,
        )

    @staticmethod
    def _scheduled_jobs(scheduler: Mapping[str, Any]) -> list[dict[str, Any]]:
        schedule = scheduler.get("schedule", {})
        if not isinstance(schedule, Mapping):
            return []
        jobs = schedule.get("jobs", {})
        if not isinstance(jobs, Mapping):
            return []
        public: list[dict[str, Any]] = []
        for name, job in islice(jobs.items(), _MAX_LIST_ITEMS):
            if not isinstance(job, Mapping):
                continue
            entry = {"name": _sanitize_text(str(name))}
            entry.update(
                _allowlisted_fields(job, ("enabled", "time", "next_occurrence"))
            )
            public.append(entry)
        return public

    @staticmethod
    def _public_scheduler(
        scheduler: Mapping[str, Any],
        scheduled_jobs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        public = _allowlisted_fields(scheduler, ("next_occurrence",))
        schedule = scheduler.get("schedule", {})
        if isinstance(schedule, Mapping):
            public["schedule"] = _allowlisted_fields(
                schedule, ("timezone", "grace_minutes")
            )
            public["schedule"]["jobs"] = scheduled_jobs
        runtime = scheduler.get("runtime", {})
        if isinstance(runtime, Mapping):
            public["runtime"] = _allowlisted_fields(
                runtime,
                ("enabled_jobs", "use_llm", "live_tools", "agents", "coach_mode"),
            )
            if runtime.get("webhook_url"):
                public["runtime"]["webhook_configured"] = True
        health = scheduler.get("health", {})
        if isinstance(health, Mapping):
            public["health"] = _allowlisted_fields(
                health, ("notification_flush_failures", "last_tick_error")
            )
        return public

    def _build_goals(self) -> dict[str, Any]:
        goals = []
        for goal in _bounded_records(self._state().get("goals", []), _MAX_STATE_SCAN):
            public = _public_record(
                goal,
                (
                    "id",
                    "title",
                    "description",
                    "cadence_days",
                    "status",
                    "created_at",
                    "last_check_in",
                    "check_ins",
                ),
            )
            if public is not None:
                goals.append(public)
            if len(goals) >= self.MAX_SECTION_ITEMS:
                break
        goals.sort(
            key=lambda item: (
                item.get("status") != "active",
                item.get("created_at", ""),
            )
        )
        return {"items": goals, "total": len(goals)}

    def _build_habits(self, now: datetime) -> dict[str, Any]:
        today = now.astimezone(self._timezone).date()
        items: list[dict[str, Any]] = []
        for habit in _bounded_records(self._state().get("habits", []), _MAX_STATE_SCAN):
            public = _public_record(
                habit,
                (
                    "id",
                    "name",
                    "description",
                    "goal_id",
                    "cadence",
                    "weekdays",
                    "target_count",
                    "status",
                    "created_at",
                    "archived_at",
                    "check_ins",
                ),
            )
            if public is None:
                continue
            public["summary"] = habit_summary(dict(habit), today)
            items.append(public)
            if len(items) >= self.MAX_SECTION_ITEMS:
                break
        items.sort(
            key=lambda item: (item.get("status") != "active", item.get("name", ""))
        )
        return {"items": items, "total": len(items)}

    def _build_projects(self) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for project in _bounded_records(
            self._state().get("projects", []), _MAX_STATE_SCAN
        ):
            public = _public_record(
                project,
                (
                    "id",
                    "name",
                    "description",
                    "status",
                    "priority",
                    "target_date",
                    "goal_ids",
                    "task_ids",
                    "milestones",
                    "progress_entries",
                    "created_at",
                    "updated_at",
                    "archived_at",
                ),
            )
            if public is None:
                continue
            public["summary"] = project_summary(dict(project))
            items.append(public)
            if len(items) >= self.MAX_SECTION_ITEMS:
                break
        items.sort(
            key=lambda item: (
                item.get("status") == "archived",
                item.get("priority", 99),
                item.get("target_date") or "9999-12-31",
            )
        )
        return {"items": items, "total": len(items)}

    def _build_suggestions(self, now: datetime) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for suggestion in _bounded_records(
            self._state().get("suggestions", []), _MAX_STATE_SCAN
        ):
            if not isinstance(suggestion, Mapping):
                continue
            try:
                expires = datetime.fromisoformat(str(suggestion.get("expires_at")))
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=UTC)
            except ValueError:
                continue
            if expires <= now:
                continue
            public = _public_record(
                suggestion,
                (
                    "id",
                    "kind",
                    "title",
                    "reason",
                    "confidence",
                    "source_ids",
                    "source_types",
                    "context",
                    "created_at",
                    "expires_at",
                    "status",
                    "accepted_at",
                    "dismissed_at",
                ),
            )
            if public is None:
                continue
            action = suggestion.get("action")
            public["action"] = (
                {"type": _sanitize_text(str(action.get("type")))}
                if isinstance(action, Mapping) and action.get("type")
                else {}
            )
            items.append(public)
            if len(items) >= self.MAX_SECTION_ITEMS:
                break
        return {"items": items, "total": len(items)}

    def _build_memory(self, now: datetime) -> dict[str, Any]:
        memories: list[dict[str, Any]] = []
        for raw in _bounded_records(self._state().get("memories", []), _MAX_STATE_SCAN):
            try:
                bounded = _bounded_raw_memory(raw)
                if bounded is None:
                    continue
                if not is_memory_eligible(
                    bounded,
                    privacy=self._memory_privacy,
                    include_archived=False,
                    now=now,
                ):
                    continue
                normalized = normalize_memory(bounded, now=now)
            except Exception:
                continue
            public = _public_record(
                normalized,
                (
                    "id",
                    "text",
                    "tags",
                    "created_at",
                    "updated_at",
                    "privacy",
                    "importance",
                    "importance_source",
                    "pinned",
                    "status",
                    "expires_at",
                ),
            )
            if public is not None:
                memories.append(public)
            if len(memories) >= self.MAX_SECTION_ITEMS:
                break
        memories.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return {"items": memories, "total": len(memories)}

    def _build_activity(self) -> dict[str, Any]:
        sources = {
            "tools": (
                self._tool_audit,
                ("at", "tool", "operation", "status", "error"),
            ),
            "mcp": (
                self._mcp_audit,
                (
                    "at",
                    "action",
                    "server",
                    "tool",
                    "status",
                    "error",
                    "duration_ms",
                    "attempt_count",
                ),
            ),
            "agents": (
                self._agent_traces,
                (
                    "run_id",
                    "workflow",
                    "started_at",
                    "completed_at",
                    "status",
                    "duration_ms",
                    "budget",
                ),
            ),
            "automations": (
                self._automation_audit,
                (
                    "at",
                    "action",
                    "type",
                    "policy",
                    "decision",
                    "status",
                    "duration_ms",
                    "error_code",
                    "summary",
                ),
            ),
        }
        activity: dict[str, list[dict[str, Any]]] = {}
        for name, (source, fields) in sources.items():
            records = []
            for record in self._recent(source):
                public = _public_record(record, fields)
                if public is not None:
                    records.append(public)
            activity[name] = records
        return activity

    def _build_settings(self) -> dict[str, Any]:
        if self._settings is None:
            return {}
        settings = self._settings()
        if not isinstance(settings, Mapping):
            raise TypeError("Dashboard settings source must return a mapping.")
        return _public_settings(settings)


class _DashboardHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _DashboardHTTPServerV6(_DashboardHTTPServer):
    address_family = socket.AF_INET6


class DashboardServer:
    """Serve the permission-bounded Nexus dashboard on a loopback address."""

    _ASSETS = {
        "/": ("index.html", "text/html; charset=utf-8"),
        "/index.html": ("index.html", "text/html; charset=utf-8"),
        "/dashboard.css": ("dashboard.css", "text/css; charset=utf-8"),
        "/dashboard.js": ("dashboard.js", "text/javascript; charset=utf-8"),
    }

    def __init__(
        self,
        snapshot: DashboardSnapshot,
        *,
        actions: DashboardActions | None = None,
        host: str = "127.0.0.1",
        port: int = 8765,
        max_snapshot_bytes: int = 1_048_576,
        max_request_bytes: int = 16_384,
    ) -> None:
        self.host = self._validate_host(host)
        if (
            not isinstance(port, int)
            or isinstance(port, bool)
            or not 0 <= port <= 65535
        ):
            raise ValueError("port must be an integer from 0 to 65535.")
        if max_snapshot_bytes < 1024:
            raise ValueError("max_snapshot_bytes must be at least 1024.")
        if max_request_bytes < 1 or max_request_bytes > 16_384:
            raise ValueError("max_request_bytes must be from 1 to 16384.")
        self._snapshot = snapshot
        self._actions = actions
        self._max_snapshot_bytes = max_snapshot_bytes
        self._max_request_bytes = max_request_bytes
        self.csrf_token = secrets.token_urlsafe(32)
        self._thread: threading.Thread | None = None
        self._closed = False
        server_type = (
            _DashboardHTTPServerV6
            if ipaddress.ip_address(self.host).version == 6
            else _DashboardHTTPServer
        )
        self._httpd = server_type((self.host, port), self._handler_type())
        self.port = int(self._httpd.server_address[1])

    @staticmethod
    def _validate_host(host: str) -> str:
        if not isinstance(host, str) or not host.strip():
            raise ValueError("Dashboard host must be a loopback address.")
        normalized = host.strip().casefold()
        if normalized == "localhost":
            return "127.0.0.1"
        try:
            address = ipaddress.ip_address(normalized)
        except ValueError as error:
            raise ValueError("Dashboard host must be a loopback address.") from error
        if not address.is_loopback:
            raise ValueError("Dashboard host must be a loopback address.")
        return str(address)

    @property
    def url(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}"

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> DashboardServer:
        if self._closed:
            raise RuntimeError("Dashboard server has been shut down.")
        if self.is_running:
            return self
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="nexus-dashboard",
            daemon=True,
        )
        self._thread.start()
        return self

    def shutdown(self) -> None:
        if self._closed:
            return
        if self.is_running:
            self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._closed = True

    def __enter__(self) -> DashboardServer:
        return self.start()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.shutdown()

    def _host_allowed(self, raw_host: str) -> bool:
        if not raw_host or any(character.isspace() for character in raw_host):
            return False
        try:
            parsed = urlsplit(f"//{raw_host}")
            hostname = parsed.hostname
            port = parsed.port
        except ValueError:
            return False
        if (
            not hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or port != self.port
        ):
            return False
        if hostname.casefold() == "localhost":
            return True
        try:
            return ipaddress.ip_address(hostname) == ipaddress.ip_address(self.host)
        except ValueError:
            return False

    def _origin_allowed(self, raw_origin: str) -> bool:
        try:
            parsed = urlsplit(raw_origin)
            port = parsed.port
        except ValueError:
            return False
        if (
            parsed.scheme != "http"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or port != self.port
        ):
            return False
        host = parsed.hostname
        if host is None:
            return False
        if host.casefold() == "localhost":
            return True
        try:
            return ipaddress.ip_address(host) == ipaddress.ip_address(self.host)
        except ValueError:
            return False

    def _handler_type(self) -> type[BaseHTTPRequestHandler]:
        owner = self

        class DashboardRequestHandler(BaseHTTPRequestHandler):
            server_version = "NexusDashboard/1"

            def do_GET(self) -> None:
                if not self._trusted_request():
                    self._send_error(403, "forbidden")
                    return
                parsed = urlsplit(self.path)
                raw_path = parsed.path
                if (
                    parsed.scheme
                    or parsed.netloc
                    or parsed.query
                    or parsed.fragment
                    or "%" in raw_path
                ):
                    self._send_error(404, "not_found")
                    return
                try:
                    path = unquote(raw_path, errors="strict")
                except (UnicodeDecodeError, ValueError):
                    self._send_error(404, "not_found")
                    return
                if path != raw_path:
                    self._send_error(404, "not_found")
                    return
                if path == "/api/snapshot":
                    self._send_snapshot()
                    return
                asset = owner._ASSETS.get(path)
                if asset is None:
                    self._send_error(404, "not_found")
                    return
                name, content_type = asset
                try:
                    payload = (
                        resources.files("nexus")
                        .joinpath("dashboard", name)
                        .read_bytes()
                    )
                except (FileNotFoundError, OSError):
                    self._send_error(404, "not_found")
                    return
                if name == "index.html":
                    payload = payload.replace(
                        b"__NEXUS_CSRF_TOKEN__",
                        owner.csrf_token.encode("ascii"),
                    )
                self._send(200, payload, content_type)

            def do_POST(self) -> None:
                if not self._trusted_request(require_origin=True):
                    self._send_error(403, "forbidden")
                    return
                parsed = urlsplit(self.path)
                raw_path = parsed.path
                if (
                    parsed.scheme
                    or parsed.netloc
                    or parsed.query
                    or parsed.fragment
                    or "%" in raw_path
                    or unquote(raw_path, errors="replace") != raw_path
                ):
                    self._send_error(404, "not_found")
                    return
                content_types = self.headers.get_all("Content-Type", failobj=[])
                if (
                    len(content_types) != 1
                    or content_types[0].split(";", 1)[0].strip().casefold()
                    != "application/json"
                ):
                    self._send_error(415, "unsupported_media_type")
                    return
                csrf_headers = self.headers.get_all("X-Nexus-CSRF", failobj=[])
                if len(csrf_headers) != 1 or not secrets.compare_digest(
                    csrf_headers[0], owner.csrf_token
                ):
                    self._send_error(403, "invalid_csrf")
                    return
                lengths = self.headers.get_all("Content-Length", failobj=[])
                try:
                    length = int(lengths[0]) if len(lengths) == 1 else -1
                except ValueError:
                    length = -1
                if length < 0:
                    self._send_error(411, "length_required")
                    return
                if length > owner._max_request_bytes:
                    if length <= owner._max_request_bytes * 4:
                        self.rfile.read(length)
                    else:
                        self.close_connection = True
                    self._send_error(413, "request_too_large")
                    return
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._send_error(400, "invalid_json")
                    return
                if not isinstance(payload, dict):
                    self._send_error(400, "invalid_request")
                    return
                if owner._actions is None:
                    self._send_error(503, "actions_unavailable")
                    return
                try:
                    result = owner._actions.dispatch(raw_path, payload)
                except (TypeError, ValueError):
                    self._send_error(400, "invalid_request")
                    return
                except Exception:
                    self._send_error(500, "action_failed")
                    return
                if result is None:
                    self._send_error(404, "not_found")
                    return
                self._send_json(200, {"status": "ok", "result": result})

            def do_PUT(self) -> None:
                self._send_error(405, "method_not_allowed")

            do_PATCH = do_PUT
            do_DELETE = do_PUT

            def _trusted_request(self, require_origin: bool = False) -> bool:
                host_headers = self.headers.get_all("Host", failobj=[])
                if len(host_headers) != 1 or not owner._host_allowed(host_headers[0]):
                    return False
                origin_headers = self.headers.get_all("Origin", failobj=[])
                if require_origin:
                    return len(origin_headers) == 1 and owner._origin_allowed(
                        origin_headers[0]
                    )
                return len(origin_headers) <= 1 and (
                    not origin_headers or owner._origin_allowed(origin_headers[0])
                )

            def _send_snapshot(self) -> None:
                try:
                    payload = json.dumps(
                        owner._snapshot.build(),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode("utf-8")
                except Exception:
                    payload = b'{"error":"snapshot_unavailable"}'
                    self._send(503, payload, "application/json; charset=utf-8")
                    return
                if len(payload) > owner._max_snapshot_bytes:
                    payload = b'{"error":"snapshot_too_large"}'
                    self._send(503, payload, "application/json; charset=utf-8")
                    return
                self._send(200, payload, "application/json; charset=utf-8")

            def _send_json(self, status: int, value: Any) -> None:
                try:
                    payload = json.dumps(
                        value, ensure_ascii=False, separators=(",", ":")
                    ).encode("utf-8")
                except (TypeError, ValueError):
                    self._send_error(500, "response_unavailable")
                    return
                if len(payload) > owner._max_snapshot_bytes:
                    self._send_error(500, "response_too_large")
                    return
                self._send(status, payload, "application/json; charset=utf-8")

            def _send_error(self, status: int, code: str) -> None:
                payload = json.dumps({"error": code}, separators=(",", ":")).encode(
                    "ascii"
                )
                self._send(status, payload, "application/json; charset=utf-8")

            def _send(self, status: int, payload: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Cross-Origin-Resource-Policy", "same-origin")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
                    "base-uri 'none'; frame-ancestors 'none'",
                )
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: Any) -> None:
                return

        return DashboardRequestHandler
