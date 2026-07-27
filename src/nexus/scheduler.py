from __future__ import annotations

import re

import time
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta

from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from .runtime_config import RUNTIME_JOB_NAMES, ProfileSettings, RuntimeSettings


_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class ProactiveScheduler:
    """Run configured proactive jobs once per scheduled local occurrence."""

    MAX_HISTORY = 100
    STATUS_HISTORY_LIMIT = 20
    CLAIM_RETENTION_DAYS = 7

    _SCHEDULE_FIELDS = {
        "morning_briefing": "morning_time",
        "evening_review": "evening_time",
        "stale_goal_reminders": "reminder_time",
    }
    _SAFE_ERROR_CODES = {
        "job_execution_failed",
        "scheduler_state_failed",
    }
    _SAFE_DEGRADATIONS = {
        "agent_execution_failed",
        "agent_partial",
        "agent_unavailable",
        "llm_fallback",
        "notification_delivery_failed",
        "notification_publish_failed",
        "tool_context_failed",
        "tool_context_invalid",
        "tool_context_partial",
        "tool_unavailable",
    }

    def __init__(
        self,
        store: Any,
        service: Any,
        notifications: Any,
        profile: ProfileSettings,
        runtime: RuntimeSettings,
        *,
        tool_manager: Any | None = None,
        orchestrator: Any | None = None,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.store = store
        self.service = service
        self.notifications = notifications
        self.profile = profile
        self.runtime = runtime
        self.tool_manager = tool_manager
        self.orchestrator = orchestrator
        self._timezone = ZoneInfo(profile.timezone)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleeper = sleeper or time.sleep
        self._notification_flush_failures = 0
        self._last_tick_error: str | None = None

    def tick(self, now: datetime | None = None) -> list[dict[str, Any]]:
        local_now = self._local_now(now)
        outcomes: list[dict[str, Any]] = []
        try:
            self.notifications.flush_deferred()
        except Exception:
            self._notification_flush_failures += 1
            self._last_tick_error = "notification_flush_failed"

        else:
            self._last_tick_error = None

        enabled = set(self.runtime.enabled_jobs)
        for job in RUNTIME_JOB_NAMES:
            if job not in enabled:
                continue
            occurrence_date = self._due_occurrence(job, local_now)
            if occurrence_date is None:
                continue
            try:
                outcome = self._run_occurrence(
                    job,
                    local_now,
                    trigger="scheduled",
                    occurrence_date=occurrence_date,
                )
            except Exception:
                outcome = self._ephemeral_error(job, local_now, "scheduled")
            if outcome is not None:
                outcomes.append(outcome)
        return outcomes

    def run_job(
        self,
        job: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self._validate_job(job)
        local_now = self._local_now(now)
        outcome = self._run_occurrence(
            job,
            local_now,
            trigger="manual",
            occurrence_date=local_now.date(),
        )
        if outcome is None:
            raise RuntimeError("Manual scheduler occurrence was not created.")
        return outcome

    def run_forever(
        self,
        stop_event: Any | None = None,
        max_ticks: int | None = None,
    ) -> dict[str, int]:
        if max_ticks is not None and (
            not isinstance(max_ticks, int)
            or isinstance(max_ticks, bool)
            or max_ticks < 0
        ):
            raise ValueError("max_ticks must be a non-negative integer or None.")

        ticks = 0
        errors = 0
        while max_ticks is None or ticks < max_ticks:
            if stop_event is not None and stop_event.is_set():
                break
            try:
                self.tick()
            except Exception:
                errors += 1
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                break
            if stop_event is not None and stop_event.is_set():
                break
            self._sleeper(self.runtime.poll_interval_seconds)
        return {"ticks": ticks, "errors": errors}

    def scheduler_status(self, now: datetime | None = None) -> dict[str, Any]:
        local_now = self._local_now(now)
        state = self.store.load()
        runs = self._state_runs(state)
        claims = {
            tuple(key.split("|", 1)) for key in self._state_claims(state) if "|" in key
        }

        jobs: dict[str, dict[str, Any]] = {}
        next_datetimes: list[datetime] = []
        enabled = set(self.runtime.enabled_jobs)
        for job in RUNTIME_JOB_NAMES:
            next_occurrence = None
            if job in enabled:
                candidate = self._next_occurrence(job, local_now, claims)
                next_occurrence = candidate.isoformat()
                next_datetimes.append(candidate)
            jobs[job] = {
                "enabled": job in enabled,
                "time": self._schedule_text(job),
                "next_occurrence": next_occurrence,
            }

        recent_runs = []
        for run in reversed(runs[-self.STATUS_HISTORY_LIMIT :]):
            safe = self._safe_run(run)
            if safe is not None:
                recent_runs.append(safe)

        return {
            "runtime": self.runtime.masked(),
            "schedule": {
                "timezone": self.profile.timezone,
                "grace_minutes": self.runtime.grace_minutes,
                "jobs": jobs,
            },
            "next_occurrence": (
                min(next_datetimes).isoformat() if next_datetimes else None
            ),
            "recent_runs": recent_runs,
            "health": {
                "notification_flush_failures": self._notification_flush_failures,
                "last_tick_error": self._last_tick_error,
            },
        }

    def _run_occurrence(
        self,
        job: str,
        local_now: datetime,
        *,
        trigger: str,
        occurrence_date: date,
    ) -> dict[str, Any] | None:
        run = {
            "id": uuid4().hex,
            "job": job,
            "trigger": trigger,
            "local_date": occurrence_date.isoformat(),
            "status": "running",
            "started_at": self._utc_iso(local_now),
            "completed_at": None,
            "error_code": None,
            "notification_id": None,
            "degradations": [],
        }
        if not self._claim(run):
            return None

        result: dict[str, Any] | None = None
        degradations: list[str] = []
        try:
            result, degradations = self._execute_job(job, local_now)
            notification = self._notification_payload(job, result)
            if notification is not None:
                kind, title, body = notification
                try:
                    record = self.notifications.publish(
                        kind,
                        title,
                        body,
                        metadata={
                            "job": job,
                            "trigger": trigger,
                            "local_date": occurrence_date.isoformat(),
                        },
                    )
                except Exception:
                    self._add_degradation(degradations, "notification_publish_failed")
                else:
                    if isinstance(record, Mapping):
                        notification_id = record.get("id")
                        if isinstance(notification_id, str):
                            run["notification_id"] = notification_id
                        if record.get("status") in {"partial", "failed"}:
                            self._add_degradation(
                                degradations, "notification_delivery_failed"
                            )
            run["status"] = "partial" if degradations else "success"
        except Exception:
            run["status"] = "error"
            run["error_code"] = "job_execution_failed"

        run["degradations"] = degradations
        run["completed_at"] = self._utc_iso(local_now)
        self._update_run(run)
        return {**run, "result": result}

    def _execute_job(
        self,
        job: str,
        local_now: datetime,
    ) -> tuple[dict[str, Any], list[str]]:
        if job == "morning_briefing":
            return self._run_morning(local_now)
        if job == "evening_review":
            return self._run_evening(local_now)
        if job == "stale_goal_reminders":
            response = self.service.proactive_review(now=local_now)
            self._require_mapping(response)
            return response, []
        raise ValueError(f"Unknown scheduler job '{job}'.")

    def _run_morning(
        self,
        local_now: datetime,
    ) -> tuple[dict[str, Any], list[str]]:
        degradations: list[str] = []
        external_context = self._briefing_context(local_now, degradations)
        tool_context_failed = self.runtime.live_tools and external_context is None

        if tool_context_failed:
            response = self._local_briefing(local_now, None, use_llm=False)
        elif self.runtime.agents and self.orchestrator is not None:
            try:
                response = self.orchestrator.run_briefing(
                    user_name=self.profile.display_name,
                    now=local_now,
                    use_llm=self.runtime.use_llm,
                    external_context=external_context,
                )
                self._require_job_response(response, "briefing")
            except Exception:
                self._add_degradation(degradations, "agent_execution_failed")
                response = self._local_briefing(
                    local_now, external_context, use_llm=False
                )
        elif self.runtime.agents:
            self._add_degradation(degradations, "agent_unavailable")
            response = self._local_briefing(local_now, external_context, use_llm=False)
        else:
            response = self._local_briefing(
                local_now,
                external_context,
                use_llm=self.runtime.use_llm,
            )

        self._require_job_response(response, "briefing")
        self._response_degradations(response, degradations)
        return response, degradations

    def _run_evening(
        self,
        local_now: datetime,
    ) -> tuple[dict[str, Any], list[str]]:
        degradations: list[str] = []
        if self.runtime.agents and self.orchestrator is not None:
            try:
                response = self.orchestrator.run_review(
                    user_name=self.profile.display_name,
                    now=local_now,
                    use_llm=self.runtime.use_llm,
                    coach_mode=self.runtime.coach_mode,
                )
                self._require_job_response(response, "review")
            except Exception:
                self._add_degradation(degradations, "agent_execution_failed")
                response = self._local_review(local_now, use_llm=False)
        elif self.runtime.agents:
            self._add_degradation(degradations, "agent_unavailable")
            response = self._local_review(local_now, use_llm=False)
        else:
            response = self._local_review(
                local_now,
                use_llm=self.runtime.use_llm,
            )

        self._require_job_response(response, "review")
        self._response_degradations(response, degradations)
        return response, degradations

    def _local_briefing(
        self,
        local_now: datetime,
        external_context: dict[str, Any] | None,
        *,
        use_llm: bool,
    ) -> dict[str, Any]:
        return self.service.daily_briefing(
            user_name=self.profile.display_name,
            now=local_now,
            use_llm=use_llm,
            external_context=external_context,
        )

    def _local_review(
        self,
        local_now: datetime,
        *,
        use_llm: bool,
    ) -> dict[str, Any]:
        return self.service.daily_review(
            user_name=self.profile.display_name,
            now=local_now,
            use_llm=use_llm,
            coach_mode=self.runtime.coach_mode,
        )

    def _briefing_context(
        self,
        local_now: datetime,
        degradations: list[str],
    ) -> dict[str, Any] | None:
        if not self.runtime.live_tools:
            return None
        if self.tool_manager is None:
            self._add_degradation(degradations, "tool_unavailable")
            return None
        try:
            context = self.tool_manager.briefing_context(local_now)
        except Exception:
            self._add_degradation(degradations, "tool_context_failed")
            return None
        if not isinstance(context, dict):
            self._add_degradation(degradations, "tool_context_invalid")
            return None
        if context.get("errors"):
            self._add_degradation(degradations, "tool_context_partial")
        return context

    def _response_degradations(
        self,
        response: Mapping[str, Any],
        degradations: list[str],
    ) -> None:
        agents = response.get("agents")
        if isinstance(agents, Mapping) and agents.get("status") != "completed":
            self._add_degradation(degradations, "agent_partial")
        llm = response.get("llm")
        if isinstance(llm, Mapping) and llm.get("error"):
            self._add_degradation(degradations, "llm_fallback")

    @staticmethod
    def _notification_payload(
        job: str,
        response: Mapping[str, Any],
    ) -> tuple[str, str, str] | None:
        if job == "morning_briefing":
            body = response.get("briefing")
            if not isinstance(body, str):
                raise ValueError("Morning briefing response is missing text.")
            return "morning_briefing", "Morning briefing", body
        if job == "evening_review":
            body = response.get("review")
            if not isinstance(body, str):
                raise ValueError("Evening review response is missing text.")
            return "evening_review", "Evening review", body
        reminders = response.get("reminders")
        if not isinstance(reminders, list) or any(
            not isinstance(item, str) for item in reminders
        ):
            raise ValueError("Reminder response is malformed.")
        if not reminders:
            return None
        return "stale_goal_reminders", "Proactive reminders", "\n".join(reminders)

    def _claim(self, run: dict[str, Any]) -> bool:
        def mutation(state: dict[str, Any]) -> bool:
            runs = self._sanitize_history(self._state_runs(state))
            claims = self._sanitize_claims(self._state_claims(state))
            self._prune_claims(claims, date.fromisoformat(run["local_date"]))
            claim_key = self._claim_key(run["job"], run["local_date"])
            if run["trigger"] == "scheduled" and claim_key in claims:
                state["runtime"]["job_runs"] = runs[-self.MAX_HISTORY :]
                state["runtime"]["occurrence_claims"] = claims
                return False
            if run["trigger"] == "scheduled":
                claims[claim_key] = {"claimed_at": run["started_at"]}
            safe_run = self._safe_run(run)
            if safe_run is not None:
                runs.append(safe_run)
            state["runtime"]["job_runs"] = runs[-self.MAX_HISTORY :]
            state["runtime"]["occurrence_claims"] = claims
            return True

        return bool(self.store.mutate(mutation))

    def _update_run(self, run: dict[str, Any]) -> None:
        def mutation(state: dict[str, Any]) -> None:
            runs = self._sanitize_history(self._state_runs(state))
            safe_run = self._safe_run(run)
            if safe_run is None:
                return
            for index, existing in enumerate(runs):
                if existing.get("id") == run["id"]:
                    runs[index] = safe_run
                    break
            else:
                runs.append(safe_run)
            state["runtime"]["job_runs"] = runs[-self.MAX_HISTORY :]
            state["runtime"]["occurrence_claims"] = self._sanitize_claims(
                self._state_claims(state)
            )

        self.store.mutate(mutation)

    @staticmethod
    def _state_runs(state: dict[str, Any]) -> list[dict[str, Any]]:
        runtime = state.setdefault("runtime", {})
        if not isinstance(runtime, dict):
            runtime = {}
            state["runtime"] = runtime
        runs = runtime.setdefault("job_runs", [])
        if not isinstance(runs, list):
            runs = []
            runtime["job_runs"] = runs
        return runs

    @staticmethod
    def _state_claims(state: dict[str, Any]) -> dict[str, Any]:
        runtime = state.setdefault("runtime", {})
        if not isinstance(runtime, dict):
            runtime = {}
            state["runtime"] = runtime
        claims = runtime.setdefault("occurrence_claims", {})
        if not isinstance(claims, dict):
            claims = {}
            runtime["occurrence_claims"] = claims
        return claims

    def _sanitize_history(self, runs: list[Any]) -> list[dict[str, Any]]:
        sanitized = []
        for run in runs:
            if not isinstance(run, Mapping):
                continue
            safe = self._safe_run(run)
            if safe is not None:
                sanitized.append(safe)
        return sanitized

    def _sanitize_claims(self, claims: Mapping[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, value in claims.items():
            if not isinstance(key, str) or "|" not in key:
                continue
            job, local_date = key.split("|", 1)
            if job not in RUNTIME_JOB_NAMES or self._safe_date(local_date) is None:
                continue
            claimed_at = value.get("claimed_at") if isinstance(value, Mapping) else None
            sanitized[self._claim_key(job, local_date)] = {
                "claimed_at": self._safe_timestamp(claimed_at)
            }
        return sanitized

    def _prune_claims(self, claims: dict[str, Any], current_date: date) -> None:
        retention_days = max(
            self.CLAIM_RETENTION_DAYS,
            self.runtime.grace_minutes // (24 * 60) + 2,
        )
        cutoff = current_date - timedelta(days=retention_days)
        for key in list(claims):
            _, local_date = key.split("|", 1)
            if date.fromisoformat(local_date) < cutoff:
                del claims[key]

    @staticmethod
    def _claim_key(job: str, local_date: str) -> str:
        return f"{job}|{local_date}"

    def _due_occurrence(
        self,
        job: str,
        local_now: datetime,
    ) -> date | None:
        current_minute = local_now.replace(second=0, microsecond=0)
        lookback_days = self.runtime.grace_minutes // (24 * 60) + 1
        for offset in range(lookback_days + 1):
            occurrence_date = local_now.date() - timedelta(days=offset)
            scheduled = self._scheduled_at(job, occurrence_date)
            if (
                scheduled
                <= current_minute
                <= scheduled + timedelta(minutes=self.runtime.grace_minutes)
            ):
                return occurrence_date
        return None

    def _next_occurrence(
        self,
        job: str,
        local_now: datetime,
        claims: set[tuple[Any, Any]],
    ) -> datetime:
        current_minute = local_now.replace(second=0, microsecond=0)
        due_date = self._due_occurrence(job, local_now)
        if due_date is not None and (job, due_date.isoformat()) not in claims:
            return self._scheduled_at(job, due_date)

        candidate_date = local_now.date()
        candidate = self._scheduled_at(job, candidate_date)
        claimed = (job, candidate_date.isoformat()) in claims
        if claimed or current_minute > candidate + timedelta(
            minutes=self.runtime.grace_minutes
        ):
            candidate = self._scheduled_at(job, candidate_date + timedelta(days=1))
        return candidate

    def _scheduled_at(self, job: str, occurrence_date: date) -> datetime:
        hour, minute = (int(part) for part in self._schedule_text(job).split(":"))
        return datetime(
            occurrence_date.year,
            occurrence_date.month,
            occurrence_date.day,
            hour,
            minute,
            tzinfo=self._timezone,
        )

    def _schedule_text(self, job: str) -> str:
        return str(getattr(self.runtime, self._SCHEDULE_FIELDS[job]))

    def _local_now(self, now: datetime | None = None) -> datetime:
        current = now if now is not None else self._clock()
        if current.tzinfo is None:
            current = current.replace(tzinfo=self._timezone)
        return current.astimezone(self._timezone)

    @staticmethod
    def _utc_iso(value: datetime) -> str:
        return value.astimezone(UTC).replace(microsecond=0).isoformat()

    @staticmethod
    def _require_mapping(response: Any) -> None:
        if not isinstance(response, dict):
            raise ValueError("Scheduler job returned an invalid response.")

    @staticmethod
    def _require_job_response(response: Any, text_field: str) -> None:
        if not isinstance(response, dict) or not isinstance(
            response.get(text_field), str
        ):
            raise ValueError("Scheduler job returned an invalid response.")

    @staticmethod
    def _add_degradation(degradations: list[str], code: str) -> None:
        if code not in degradations:
            degradations.append(code)

    @staticmethod
    def _validate_job(job: str) -> None:
        if job not in RUNTIME_JOB_NAMES:
            raise ValueError(f"Unknown scheduler job '{job}'.")

    def _ephemeral_error(
        self,
        job: str,
        local_now: datetime,
        trigger: str,
    ) -> dict[str, Any]:
        timestamp = self._utc_iso(local_now)
        return {
            "id": None,
            "job": job,
            "trigger": trigger,
            "local_date": local_now.date().isoformat(),
            "status": "error",
            "started_at": timestamp,
            "completed_at": timestamp,
            "error_code": "scheduler_state_failed",
            "notification_id": None,
            "degradations": [],
            "result": None,
        }

    def _safe_run(self, run: Mapping[str, Any]) -> dict[str, Any] | None:
        job = run.get("job")
        if job not in RUNTIME_JOB_NAMES:
            return None
        trigger = run.get("trigger")
        if trigger not in {"scheduled", "manual"}:
            trigger = "manual"
        status = run.get("status")
        if status not in {"running", "success", "partial", "error"}:
            status = "error"
        error_code = run.get("error_code")
        if error_code not in self._SAFE_ERROR_CODES:
            error_code = None if error_code is None else "job_execution_failed"
        degradations = run.get("degradations")
        safe_degradations = (
            [
                item
                for item in degradations
                if isinstance(item, str) and item in self._SAFE_DEGRADATIONS
            ]
            if isinstance(degradations, list)
            else []
        )
        return {
            "id": self._safe_identifier(run.get("id")),
            "job": job,
            "trigger": trigger,
            "local_date": self._safe_date(run.get("local_date")),
            "status": status,
            "started_at": self._safe_timestamp(run.get("started_at")),
            "completed_at": self._safe_timestamp(run.get("completed_at")),
            "error_code": error_code,
            "notification_id": self._safe_identifier(run.get("notification_id")),
            "degradations": safe_degradations,
        }

    @staticmethod
    def _safe_identifier(value: Any) -> str | None:
        if isinstance(value, str) and _SAFE_IDENTIFIER.fullmatch(value):
            return value
        return None

    @staticmethod
    def _safe_date(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        try:
            date.fromisoformat(value)
        except ValueError:
            return None
        return value

    @staticmethod
    def _safe_timestamp(value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or len(value) > 64:
            return None
        try:
            datetime.fromisoformat(value)
        except ValueError:
            return None
        return value
