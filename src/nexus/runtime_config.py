from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
import re
from typing import Any
import unicodedata
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .planning import COACH_MODES


RUNTIME_JOB_NAMES = (
    "morning_briefing",
    "evening_review",
    "stale_goal_reminders",
)
_CLOCK_TIME = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _host_timezone() -> str:
    timezone = datetime.now().astimezone().tzinfo
    name = getattr(timezone, "key", None)
    if isinstance(name, str):
        try:
            ZoneInfo(name)
        except ZoneInfoNotFoundError:
            pass
        else:
            return name
    return "UTC"


def _validate_clock_time(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not _CLOCK_TIME.fullmatch(value):
        raise ValueError(f"{field_name} must use HH:MM in 24-hour time.")


def _validate_webhook_url(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or any(
            character.isspace() or unicodedata.category(character) in {"Cc", "Cf"}
            for character in value
        )
    ):
        raise ValueError("webhook_url must be a valid HTTP or HTTPS URL.")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        parsed.port
    except ValueError as error:
        raise ValueError("webhook_url must be a valid HTTP or HTTPS URL.") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(
            "webhook_url must use HTTP or HTTPS, include a hostname, and omit credentials."
        )


@dataclass(frozen=True)
class ProfileSettings:
    display_name: str = "User"
    timezone: str = _host_timezone()

    def __post_init__(self) -> None:
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValueError("display_name must not be empty.")
        if not isinstance(self.timezone, str):
            raise ValueError("timezone must be an IANA timezone name.")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be an IANA timezone name.") from error

    def masked(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeSettings:
    enabled_jobs: Sequence[str] = ()
    morning_time: str = "08:00"
    evening_time: str = "20:00"
    reminder_time: str = "12:00"
    grace_minutes: int = 30
    poll_interval_seconds: int = 60
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    inbox_enabled: bool = True
    console_enabled: bool = False
    webhook_url: str | None = None
    use_llm: bool = False
    live_tools: bool = False
    agents: bool = False
    coach_mode: str = "gentle"

    def __post_init__(self) -> None:
        if isinstance(self.enabled_jobs, (str, bytes)) or not isinstance(
            self.enabled_jobs, Sequence
        ):
            raise ValueError("enabled_jobs must be a sequence of strings.")
        jobs = tuple(self.enabled_jobs)
        if any(not isinstance(job, str) for job in jobs):
            raise ValueError("enabled_jobs must be a sequence of strings.")
        unknown_jobs = set(jobs).difference(RUNTIME_JOB_NAMES)
        if unknown_jobs:
            raise ValueError(f"Unknown runtime job: {sorted(unknown_jobs)[0]}.")
        if len(jobs) != len(set(jobs)):
            raise ValueError("Runtime jobs must not be repeated.")
        object.__setattr__(self, "enabled_jobs", jobs)

        for field_name in ("morning_time", "evening_time", "reminder_time"):
            _validate_clock_time(getattr(self, field_name), field_name)
        if (self.quiet_hours_start is None) != (self.quiet_hours_end is None):
            raise ValueError("quiet_hours_start and quiet_hours_end must both be configured.")
        if self.quiet_hours_start is not None and self.quiet_hours_end is not None:
            _validate_clock_time(self.quiet_hours_start, "quiet_hours_start")
            _validate_clock_time(self.quiet_hours_end, "quiet_hours_end")
            if self.quiet_hours_start == self.quiet_hours_end:
                raise ValueError("quiet hour start and end must be different.")
        if (
            not isinstance(self.grace_minutes, int)
            or isinstance(self.grace_minutes, bool)
            or self.grace_minutes < 0
        ):
            raise ValueError("grace_minutes must be a non-negative integer.")
        if (
            not isinstance(self.poll_interval_seconds, int)
            or isinstance(self.poll_interval_seconds, bool)
            or self.poll_interval_seconds < 1
        ):
            raise ValueError("poll_interval_seconds must be a positive integer.")
        for field_name in (
            "inbox_enabled",
            "console_enabled",
            "use_llm",
            "live_tools",
            "agents",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise ValueError(f"{field_name} must be a boolean.")
        if not isinstance(self.coach_mode, str) or self.coach_mode not in COACH_MODES:
            raise ValueError(f"Unknown coach mode '{self.coach_mode}'.")
        if self.webhook_url is not None:
            _validate_webhook_url(self.webhook_url)

    def masked(self) -> dict[str, Any]:
        data = asdict(self)
        if self.webhook_url:
            data["webhook_url"] = "***configured***"
        return data


def runtime_settings_from_mapping(values: dict[str, Any]) -> RuntimeSettings:
    return RuntimeSettings(**values)


def profile_settings_from_mapping(values: dict[str, Any]) -> ProfileSettings:
    return ProfileSettings(**values)
