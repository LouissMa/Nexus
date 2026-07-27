from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from nexus.runtime_config import ProfileSettings, RuntimeSettings
from nexus.scheduler import ProactiveScheduler
from nexus.store import JsonStore, StateConflictError


class RecordingNotifications:
    def __init__(
        self,
        *,
        publish_status: str = "delivered",
        fail_publish: bool = False,
        fail_flush: bool = False,
    ):
        self.publish_status = publish_status
        self.fail_publish = fail_publish
        self.fail_flush = fail_flush
        self.flush_calls = 0
        self.published: list[dict[str, Any]] = []

    def flush_deferred(self) -> list[dict[str, Any]]:
        self.flush_calls += 1
        if self.fail_flush:
            raise RuntimeError("private flush backend secret")
        return []

    def publish(
        self,
        kind: str,
        title: str,
        body: str,
        *,
        urgency: str = "normal",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.fail_publish:
            raise RuntimeError("private notification backend details")
        item = {
            "id": f"notice-{len(self.published) + 1}",
            "kind": kind,
            "title": title,
            "body": body,
            "urgency": urgency,
            "metadata": metadata or {},
            "status": self.publish_status,
        }
        self.published.append(item)
        return item


class RecordingService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_jobs: set[str] = set()
        self.reminders: list[str] = ["Check the stale goal."]

    def daily_briefing(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("morning_briefing", kwargs))
        if "morning_briefing" in self.fail_jobs:
            raise RuntimeError("private briefing failure")
        return {
            "briefing": "Morning body",
            "llm": {"requested": kwargs["use_llm"], "used": False, "error": None},
        }

    def daily_review(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("evening_review", kwargs))
        if "evening_review" in self.fail_jobs:
            raise RuntimeError("private review failure")
        return {
            "review": "Evening body",
            "llm": {"requested": kwargs["use_llm"], "used": False, "error": None},
        }

    def proactive_review(self, now: datetime | None = None) -> dict[str, Any]:
        self.calls.append(("stale_goal_reminders", {"now": now}))
        if "stale_goal_reminders" in self.fail_jobs:
            raise RuntimeError("private reminder failure")
        return {
            "generated_at": now.isoformat() if now else None,
            "reminders": self.reminders,
        }


class RecordingToolManager:
    def __init__(self, *, fail: bool = False, include_error: bool = False) -> None:
        self.fail = fail
        self.include_error = include_error
        self.calls: list[datetime] = []

    def briefing_context(self, now: datetime | None = None) -> dict[str, Any]:
        assert now is not None
        self.calls.append(now)
        if self.fail:
            raise RuntimeError("private tool credentials")
        errors = (
            [{"tool": "weather", "error": "unavailable"}] if self.include_error else []
        )
        return {
            "weather": {"summary": "Sunny"},
            "calendar": [],
            "todos": [],
            "errors": errors,
        }


class RecordingOrchestrator:
    def __init__(
        self, *, fail_briefing: bool = False, partial_review: bool = False
    ) -> None:
        self.fail_briefing = fail_briefing
        self.partial_review = partial_review
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run_briefing(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("morning_briefing", kwargs))
        if self.fail_briefing:
            raise RuntimeError("private agent trace")
        return {
            "briefing": "Agent morning body",
            "llm": {"requested": kwargs["use_llm"], "used": False, "error": None},
            "agents": {"status": "completed"},
        }

    def run_review(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("evening_review", kwargs))
        return {
            "review": "Agent evening body",
            "llm": {"requested": kwargs["use_llm"], "used": False, "error": None},
            "agents": {"status": "partial" if self.partial_review else "completed"},
        }


def make_scheduler(
    tmp_path: Path,
    *,
    runtime: RuntimeSettings | None = None,
    profile: ProfileSettings | None = None,
    service: Any | None = None,
    notifications: Any | None = None,
    tool_manager: Any | None = None,
    orchestrator: Any | None = None,
    sleeper: Any | None = None,
) -> tuple[ProactiveScheduler, JsonStore, Any, Any]:
    store = JsonStore(tmp_path / "state.json")
    selected_service = service or RecordingService()
    selected_notifications = notifications or RecordingNotifications()
    scheduler = ProactiveScheduler(
        store,
        selected_service,
        selected_notifications,
        profile or ProfileSettings(display_name="Ava", timezone="UTC"),
        runtime or RuntimeSettings(),
        tool_manager=tool_manager,
        orchestrator=orchestrator,
        sleeper=sleeper,
    )
    return scheduler, store, selected_service, selected_notifications


@pytest.mark.parametrize(
    ("now", "expected_runs"),
    [
        (datetime(2026, 7, 27, 7, 59, 59, tzinfo=UTC), 0),
        (datetime(2026, 7, 27, 8, 0, tzinfo=UTC), 1),
        (datetime(2026, 7, 27, 8, 30, 59, tzinfo=UTC), 1),
        (datetime(2026, 7, 27, 8, 31, tzinfo=UTC), 0),
    ],
)
def test_tick_runs_only_from_scheduled_minute_through_inclusive_grace(
    tmp_path: Path,
    now: datetime,
    expected_runs: int,
) -> None:
    scheduler, _, _, notifications = make_scheduler(
        tmp_path,
        runtime=RuntimeSettings(
            enabled_jobs=("morning_briefing",),
            morning_time="08:00",
            grace_minutes=30,
        ),
    )

    runs = scheduler.tick(now)

    assert len(runs) == expected_runs
    assert notifications.flush_calls == 1


def test_tick_uses_profile_timezone_and_claims_the_scheduled_local_date(
    tmp_path: Path,
) -> None:
    scheduler, store, service, _ = make_scheduler(
        tmp_path,
        profile=ProfileSettings(display_name="Ava", timezone="Asia/Shanghai"),
        runtime=RuntimeSettings(
            enabled_jobs=("morning_briefing",),
            morning_time="07:00",
            grace_minutes=0,
        ),
    )
    utc_now = datetime(2026, 7, 26, 23, 0, tzinfo=UTC)

    run = scheduler.tick(utc_now)[0]

    assert run["local_date"] == "2026-07-27"
    assert service.calls[0][1]["now"] == datetime(
        2026, 7, 27, 7, 0, tzinfo=ZoneInfo("Asia/Shanghai")
    )
    assert store.load()["runtime"]["job_runs"][0]["local_date"] == "2026-07-27"


def test_scheduled_claim_is_saved_running_before_execution_and_survives_restart(
    tmp_path: Path,
) -> None:
    store = JsonStore(tmp_path / "state.json")

    class ClaimInspectingService(RecordingService):
        def daily_briefing(self, **kwargs: Any) -> dict[str, Any]:
            claim = store.load()["runtime"]["job_runs"][0]
            assert claim["status"] == "running"
            assert claim["completed_at"] is None
            self.calls.append(("morning_briefing", kwargs))
            raise RuntimeError("private backend message")

    service = ClaimInspectingService()
    runtime = RuntimeSettings(
        enabled_jobs=("morning_briefing",),
        morning_time="08:00",
        grace_minutes=10,
    )
    profile = ProfileSettings(timezone="UTC")
    first = ProactiveScheduler(
        store, service, RecordingNotifications(), profile, runtime
    )
    now = datetime(2026, 7, 27, 8, 5, tzinfo=UTC)

    first_run = first.tick(now)[0]
    restarted = ProactiveScheduler(
        JsonStore(store.path),
        service,
        RecordingNotifications(),
        profile,
        runtime,
    )
    second_runs = restarted.tick(now)

    assert first_run["status"] == "error"
    assert first_run["error_code"] == "job_execution_failed"
    assert second_runs == []
    assert len(service.calls) == 1
    persisted = store.load()["runtime"]["job_runs"]
    assert len(persisted) == 1
    assert persisted[0]["status"] == "error"
    assert "private backend message" not in json.dumps(persisted)


def test_manual_jobs_dispatch_response_text_and_explicit_runtime_options(
    tmp_path: Path,
) -> None:
    tool_manager = RecordingToolManager()
    runtime = RuntimeSettings(
        use_llm=True,
        live_tools=True,
        coach_mode="academic",
    )
    scheduler, _, service, notifications = make_scheduler(
        tmp_path,
        runtime=runtime,
        tool_manager=tool_manager,
    )
    now = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)

    morning = scheduler.run_job("morning_briefing", now)
    evening = scheduler.run_job("evening_review", now)
    reminder = scheduler.run_job("stale_goal_reminders", now)

    morning_args = service.calls[0][1]
    assert morning_args == {
        "user_name": "Ava",
        "now": now,
        "use_llm": True,
        "external_context": {
            "weather": {"summary": "Sunny"},
            "calendar": [],
            "todos": [],
            "errors": [],
        },
    }
    assert service.calls[1][1] == {
        "user_name": "Ava",
        "now": now,
        "use_llm": True,
        "coach_mode": "academic",
    }
    assert tool_manager.calls == [now]
    assert [item["body"] for item in notifications.published] == [
        "Morning body",
        "Evening body",
        "Check the stale goal.",
    ]
    assert [morning["status"], evening["status"], reminder["status"]] == [
        "success",
        "success",
        "success",
    ]


def test_reminder_job_does_not_publish_when_there_are_no_reminders(
    tmp_path: Path,
) -> None:
    service = RecordingService()
    service.reminders = []
    scheduler, _, _, notifications = make_scheduler(tmp_path, service=service)

    run = scheduler.run_job(
        "stale_goal_reminders", datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
    )

    assert run["status"] == "success"
    assert run["notification_id"] is None
    assert notifications.published == []


def test_agents_are_used_when_supplied_and_partial_agent_results_stay_partial(
    tmp_path: Path,
) -> None:
    orchestrator = RecordingOrchestrator(partial_review=True)
    scheduler, _, service, notifications = make_scheduler(
        tmp_path,
        runtime=RuntimeSettings(agents=True, use_llm=True, coach_mode="startup"),
        orchestrator=orchestrator,
    )
    now = datetime(2026, 7, 27, 20, 0, tzinfo=UTC)

    morning = scheduler.run_job("morning_briefing", now)
    evening = scheduler.run_job("evening_review", now)

    assert service.calls == []
    assert orchestrator.calls == [
        (
            "morning_briefing",
            {
                "user_name": "Ava",
                "now": now,
                "use_llm": True,
                "external_context": None,
            },
        ),
        (
            "evening_review",
            {
                "user_name": "Ava",
                "now": now,
                "use_llm": True,
                "coach_mode": "startup",
            },
        ),
    ]
    assert morning["status"] == "success"
    assert evening["status"] == "partial"
    assert evening["degradations"] == ["agent_partial"]
    assert [item["body"] for item in notifications.published] == [
        "Agent morning body",
        "Agent evening body",
    ]


@pytest.mark.parametrize("supply_failing_orchestrator", [False, True])
def test_missing_or_failed_agent_uses_deterministic_local_fallback(
    tmp_path: Path,
    supply_failing_orchestrator: bool,
) -> None:
    orchestrator = (
        RecordingOrchestrator(fail_briefing=True)
        if supply_failing_orchestrator
        else None
    )
    scheduler, _, service, _ = make_scheduler(
        tmp_path,
        runtime=RuntimeSettings(agents=True, use_llm=True),
        orchestrator=orchestrator,
    )

    run = scheduler.run_job("morning_briefing", datetime(2026, 7, 27, 8, 0, tzinfo=UTC))

    assert run["status"] == "partial"
    assert run["result"]["briefing"] == "Morning body"
    assert service.calls[0][1]["use_llm"] is False
    expected = "agent_execution_failed" if orchestrator else "agent_unavailable"
    assert run["degradations"] == [expected]


def test_tool_failure_and_job_failure_are_isolated_across_due_jobs(
    tmp_path: Path,
) -> None:
    service = RecordingService()
    service.fail_jobs.add("evening_review")
    tool_manager = RecordingToolManager(fail=True)
    notifications = RecordingNotifications(publish_status="partial")
    scheduler, _, _, _ = make_scheduler(
        tmp_path,
        service=service,
        notifications=notifications,
        tool_manager=tool_manager,
        runtime=RuntimeSettings(
            enabled_jobs=(
                "morning_briefing",
                "evening_review",
                "stale_goal_reminders",
            ),
            morning_time="08:00",
            evening_time="08:00",
            reminder_time="08:00",
            grace_minutes=0,
            live_tools=True,
        ),
    )

    runs = scheduler.tick(datetime(2026, 7, 27, 8, 0, tzinfo=UTC))

    assert [run["job"] for run in runs] == [
        "morning_briefing",
        "evening_review",
        "stale_goal_reminders",
    ]
    assert [run["status"] for run in runs] == ["partial", "error", "partial"]
    assert runs[0]["result"]["briefing"] == "Morning body"
    assert runs[0]["degradations"] == [
        "tool_context_failed",
        "notification_delivery_failed",
    ]
    assert runs[1]["error_code"] == "job_execution_failed"
    assert runs[2]["result"]["reminders"] == ["Check the stale goal."]
    assert tool_manager.calls == [datetime(2026, 7, 27, 8, 0, tzinfo=UTC)]


def test_notification_exception_keeps_local_result_and_marks_partial(
    tmp_path: Path,
) -> None:
    scheduler, store, _, _ = make_scheduler(
        tmp_path,
        notifications=RecordingNotifications(fail_publish=True),
    )

    run = scheduler.run_job("evening_review", datetime(2026, 7, 27, 20, 0, tzinfo=UTC))

    assert run["status"] == "partial"
    assert run["result"]["review"] == "Evening body"
    assert run["degradations"] == ["notification_publish_failed"]
    persisted = store.load()["runtime"]["job_runs"][0]
    assert persisted["notification_id"] is None
    assert "Evening body" not in json.dumps(persisted)


def test_manual_run_can_retry_a_failed_scheduled_occurrence_and_validates_job(
    tmp_path: Path,
) -> None:
    service = RecordingService()
    service.fail_jobs.add("morning_briefing")
    scheduler, store, _, _ = make_scheduler(
        tmp_path,
        service=service,
        runtime=RuntimeSettings(
            enabled_jobs=("morning_briefing",),
            morning_time="08:00",
            grace_minutes=0,
        ),
    )
    now = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)
    scheduled = scheduler.tick(now)[0]
    service.fail_jobs.clear()

    manual = scheduler.run_job("morning_briefing", now)

    assert scheduled["status"] == "error"
    assert manual["status"] == "success"
    assert [run["trigger"] for run in store.load()["runtime"]["job_runs"]] == [
        "scheduled",
        "manual",
    ]
    with pytest.raises(ValueError, match="Unknown scheduler job"):
        scheduler.run_job("nightly_cleanup", now)


def test_run_forever_is_bounded_sleeps_between_ticks_and_survives_tick_errors(
    tmp_path: Path,
) -> None:
    sleeps: list[int] = []
    scheduler, _, _, _ = make_scheduler(
        tmp_path,
        runtime=RuntimeSettings(poll_interval_seconds=7),
        sleeper=sleeps.append,
    )
    attempts = 0

    def flaky_tick(now: datetime | None = None) -> list[dict[str, Any]]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("one bad tick")
        return []

    scheduler.tick = flaky_tick  # type: ignore[method-assign]

    summary = scheduler.run_forever(max_ticks=3)

    assert summary == {"ticks": 3, "errors": 1}
    assert sleeps == [7, 7]


def test_run_forever_honors_stop_event_before_another_tick(tmp_path: Path) -> None:
    stop_event = Event()
    sleeps: list[int] = []

    def stop_after_sleep(seconds: int) -> None:
        sleeps.append(seconds)
        stop_event.set()

    scheduler, _, _, _ = make_scheduler(
        tmp_path,
        runtime=RuntimeSettings(poll_interval_seconds=9),
        sleeper=stop_after_sleep,
    )
    calls = 0

    def count_tick(now: datetime | None = None) -> list[dict[str, Any]]:
        nonlocal calls
        calls += 1
        return []

    scheduler.tick = count_tick  # type: ignore[method-assign]

    summary = scheduler.run_forever(stop_event=stop_event)

    assert summary == {"ticks": 1, "errors": 0}
    assert calls == 1
    assert sleeps == [9]


def test_scheduler_status_masks_config_and_exposes_only_safe_bounded_history(
    tmp_path: Path,
) -> None:
    secret_url = "https://hooks.example.test/private-token"
    runtime = RuntimeSettings(
        enabled_jobs=("morning_briefing",),
        morning_time="08:00",
        grace_minutes=15,
        webhook_url=secret_url,
    )
    scheduler, store, _, _ = make_scheduler(tmp_path, runtime=runtime)
    state = store.load()
    state["runtime"]["job_runs"] = [
        {
            "id": f"run-{index}",
            "job": "morning_briefing",
            "trigger": "manual",
            "local_date": "2026-07-26",
            "status": "success",
            "started_at": "2026-07-26T00:00:00+00:00",
            "completed_at": "2026-07-26T00:00:01+00:00",
            "error_code": None,
            "notification_id": f"notice-{index}",
            "degradations": [],
            "body": f"private body {index}",
            "prompt": "private prompt",
            "memory": "private memory",
        }
        for index in range(ProactiveScheduler.MAX_HISTORY + 5)
    ]
    store.save(state)

    scheduler.run_job("stale_goal_reminders", datetime(2026, 7, 27, 7, 0, tzinfo=UTC))
    status = scheduler.scheduler_status(datetime(2026, 7, 27, 7, 0, tzinfo=UTC))

    encoded = json.dumps(status)
    persisted = store.load()["runtime"]["job_runs"]
    assert len(persisted) == ProactiveScheduler.MAX_HISTORY
    assert status["runtime"]["webhook_url"] == "***configured***"
    assert status["schedule"]["timezone"] == "UTC"
    assert status["schedule"]["jobs"]["morning_briefing"]["time"] == "08:00"
    assert status["next_occurrence"] == "2026-07-27T08:00:00+00:00"
    assert len(status["recent_runs"]) == ProactiveScheduler.STATUS_HISTORY_LIMIT
    assert set(status["recent_runs"][0]) == {
        "id",
        "job",
        "trigger",
        "local_date",
        "status",
        "started_at",
        "completed_at",
        "error_code",
        "notification_id",
        "degradations",
    }
    assert secret_url not in encoded
    assert "private body" not in encoded
    assert "private prompt" not in encoded
    assert "private memory" not in encoded


def test_store_adds_runtime_job_history_without_losing_legacy_state(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "goals": [{"id": "legacy-goal"}],
                "extension": {"keep": True},
                "runtime": {"legacy_flag": "keep"},
            }
        ),
        encoding="utf-8",
    )

    state = JsonStore(path).load()

    assert state["goals"] == [{"id": "legacy-goal"}]
    assert state["extension"] == {"keep": True}
    assert state["runtime"] == {
        "job_runs": [],
        "occurrence_claims": {},
        "legacy_flag": "keep",
    }


def test_store_rejects_stale_snapshot_when_same_top_level_key_changed(
    tmp_path: Path,
) -> None:
    store = JsonStore(tmp_path / "state.json")
    first = store.load()
    stale = store.load()
    first["goals"].append({"id": "concurrent-goal"})
    store.save(first)
    stale["goals"].append({"id": "stale-goal"})

    with pytest.raises(StateConflictError, match="changed"):
        store.save(stale)

    persisted = store.load()
    assert persisted["goals"] == [{"id": "concurrent-goal"}]


def test_store_merges_stale_goal_save_with_concurrent_runtime_change(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps({"runtime": {"legacy_flag": "keep"}}),
        encoding="utf-8",
    )
    store = JsonStore(path)
    goal_writer = store.load()
    runtime_writer = store.load()
    goal_writer["goals"].append({"id": "foreground-goal"})
    runtime_writer["runtime"]["occurrence_claims"]["morning|2026-07-27"] = {
        "claimed_at": "2026-07-27T00:00:00+00:00"
    }
    store.save(runtime_writer)

    store.save(goal_writer)

    assert goal_writer["goals"] == [{"id": "foreground-goal"}]
    assert goal_writer["runtime"] == {
        "job_runs": [],
        "occurrence_claims": {
            "morning|2026-07-27": {"claimed_at": "2026-07-27T00:00:00+00:00"}
        },
        "legacy_flag": "keep",
    }
    goal_writer["memories"].append({"id": "follow-up-memory"})
    store.save(goal_writer)
    persisted = store.load()
    assert persisted["goals"] == [{"id": "foreground-goal"}]
    assert persisted["memories"] == [{"id": "follow-up-memory"}]
    assert persisted["runtime"] == goal_writer["runtime"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "revision" not in raw
    assert "base" not in raw


def test_store_mutate_reapplies_callback_after_revision_conflict(
    tmp_path: Path,
) -> None:
    store = JsonStore(tmp_path / "state.json")
    callback_calls = 0

    def add_runtime_state(state: dict[str, Any]) -> str:
        nonlocal callback_calls
        callback_calls += 1
        state["runtime"]["scheduler_marker"] = "kept"
        if callback_calls == 1:
            concurrent = store.load()
            concurrent["runtime"]["concurrent_marker"] = "kept-too"
            store.save(concurrent)
        return "mutation-result"

    result = store.mutate(add_runtime_state, retries=3)

    persisted = store.load()
    assert result == "mutation-result"
    assert callback_calls == 2
    assert persisted["runtime"]["scheduler_marker"] == "kept"
    assert persisted["runtime"]["concurrent_marker"] == "kept-too"


def test_store_atomic_write_uses_no_persisted_revision_metadata_or_leftover_temp(
    tmp_path: Path,
) -> None:
    store = JsonStore(tmp_path / "state.json")
    state = store.load()
    state["goals"].append({"id": "atomic-goal"})

    store.save(state)

    raw = json.loads(store.path.read_text(encoding="utf-8"))
    assert raw["goals"] == [{"id": "atomic-goal"}]
    assert "revision" not in raw
    assert list(tmp_path.glob(".state.json.*.tmp")) == []


def test_scheduler_mutation_retries_without_losing_concurrent_goal(
    tmp_path: Path,
) -> None:
    class ConflictInjectingStore(JsonStore):
        injected = False

        def mutate(self, callback: Any, *, retries: int = 3) -> Any:
            def wrapped(state: dict[str, Any]) -> Any:
                result = callback(state)
                if not self.injected:
                    self.injected = True
                    concurrent = self.load()
                    concurrent["goals"].append({"id": "concurrent-goal"})
                    self.save(concurrent)
                return result

            return super().mutate(wrapped, retries=retries)

    store = ConflictInjectingStore(tmp_path / "state.json")
    scheduler = ProactiveScheduler(
        store,
        RecordingService(),
        RecordingNotifications(),
        ProfileSettings(timezone="UTC"),
        RuntimeSettings(),
    )

    run = scheduler.run_job(
        "stale_goal_reminders", datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
    )

    persisted = store.load()
    assert run["status"] == "success"
    assert persisted["goals"] == [{"id": "concurrent-goal"}]
    assert persisted["runtime"]["job_runs"][0]["id"] == run["id"]


def test_scheduled_claim_survives_bounded_history_manual_run_eviction(
    tmp_path: Path,
) -> None:
    service = RecordingService()
    scheduler, store, _, _ = make_scheduler(
        tmp_path,
        service=service,
        runtime=RuntimeSettings(
            enabled_jobs=("morning_briefing",),
            morning_time="08:00",
            grace_minutes=30,
        ),
    )
    now = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)
    scheduler.tick(now)

    for _ in range(ProactiveScheduler.MAX_HISTORY + 5):
        scheduler.run_job("stale_goal_reminders", now)
    replay = scheduler.tick(now)

    state = store.load()
    assert replay == []
    assert len(state["runtime"]["job_runs"]) == ProactiveScheduler.MAX_HISTORY
    assert "morning_briefing|2026-07-27" in state["runtime"]["occurrence_claims"]
    assert [name for name, _ in service.calls].count("morning_briefing") == 1


def test_scheduler_rewrites_all_legacy_run_history_through_safe_whitelist(
    tmp_path: Path,
) -> None:
    scheduler, store, _, _ = make_scheduler(tmp_path)
    state = store.load()
    state["runtime"]["job_runs"] = [
        {
            "id": "legacy-run",
            "job": "morning_briefing",
            "trigger": "manual",
            "local_date": "2026-07-26",
            "status": "error",
            "started_at": "2026-07-26T00:00:00+00:00",
            "completed_at": "2026-07-26T00:00:01+00:00",
            "error_code": "https://secret.example/token",
            "notification_id": "https://secret.example/notice",
            "degradations": ["Bearer private-secret"],
            "prompt": "private prompt",
            "body": "private body",
            "memory": "private memory",
            "api_key": "sk-private-secret",
        }
    ]
    store.save(state)

    scheduler.run_job("stale_goal_reminders", datetime(2026, 7, 27, 12, 0, tzinfo=UTC))

    raw = json.loads(store.path.read_text(encoding="utf-8"))
    encoded = json.dumps(raw)
    allowed = {
        "id",
        "job",
        "trigger",
        "local_date",
        "status",
        "started_at",
        "completed_at",
        "error_code",
        "notification_id",
        "degradations",
    }
    assert all(set(item) == allowed for item in raw["runtime"]["job_runs"])
    assert "private prompt" not in encoded
    assert "private body" not in encoded
    assert "private memory" not in encoded
    assert "private-secret" not in encoded
    assert "secret.example" not in encoded


@pytest.mark.parametrize(
    ("tool_manager", "expected_degradation"),
    [
        (None, "tool_unavailable"),
        (RecordingToolManager(fail=True), "tool_context_failed"),
        (object(), "tool_context_invalid"),
    ],
)
def test_unavailable_live_tools_force_local_non_llm_path_without_agents(
    tmp_path: Path,
    tool_manager: Any,
    expected_degradation: str,
) -> None:
    if type(tool_manager) is object:

        class InvalidToolManager:
            def briefing_context(self, now: datetime | None = None) -> list[str]:
                return ["invalid"]

        tool_manager = InvalidToolManager()
    orchestrator = RecordingOrchestrator()
    scheduler, _, service, _ = make_scheduler(
        tmp_path,
        runtime=RuntimeSettings(live_tools=True, agents=True, use_llm=True),
        tool_manager=tool_manager,
        orchestrator=orchestrator,
    )

    run = scheduler.run_job("morning_briefing", datetime(2026, 7, 27, 8, 0, tzinfo=UTC))

    assert run["status"] == "partial"
    assert run["degradations"] == [expected_degradation]
    assert service.calls[0][1]["use_llm"] is False
    assert orchestrator.calls == []


@pytest.mark.parametrize(
    ("job", "response_field", "expected_body"),
    [
        ("morning_briefing", "briefing", "Morning body"),
        ("evening_review", "review", "Evening body"),
    ],
)
def test_malformed_agent_response_falls_back_to_deterministic_local_service(
    tmp_path: Path,
    job: str,
    response_field: str,
    expected_body: str,
) -> None:
    class MalformedOrchestrator:
        def run_briefing(self, **kwargs: Any) -> dict[str, Any]:
            return {"briefing": None, "agents": {"status": "completed"}}

        def run_review(self, **kwargs: Any) -> list[str]:
            return ["not", "a", "mapping"]

    scheduler, _, service, notifications = make_scheduler(
        tmp_path,
        runtime=RuntimeSettings(agents=True, use_llm=True),
        orchestrator=MalformedOrchestrator(),
    )

    run = scheduler.run_job(job, datetime(2026, 7, 27, 20, 0, tzinfo=UTC))

    assert run["status"] == "partial"
    assert run["result"][response_field] == expected_body
    assert run["degradations"] == ["agent_execution_failed"]
    assert service.calls[0][1]["use_llm"] is False
    assert notifications.published[0]["body"] == expected_body


def test_explicit_replay_now_keeps_completion_at_or_after_start(
    tmp_path: Path,
) -> None:
    replay_now = datetime(2030, 1, 2, 8, 0, tzinfo=UTC)
    scheduler, _, _, _ = make_scheduler(tmp_path)
    scheduler._clock = lambda: datetime(2020, 1, 1, tzinfo=UTC)

    run = scheduler.run_job("morning_briefing", replay_now)

    assert run["started_at"] == "2030-01-02T08:00:00+00:00"
    assert run["completed_at"] == "2030-01-02T08:00:00+00:00"


def test_deferred_flush_failure_is_safe_and_observable_in_tick_and_status(
    tmp_path: Path,
) -> None:
    notifications = RecordingNotifications(fail_flush=True)
    scheduler, _, _, _ = make_scheduler(tmp_path, notifications=notifications)
    now = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)

    output = scheduler.tick(now)
    status = scheduler.scheduler_status(now)

    assert output == []
    assert status["health"] == {
        "notification_flush_failures": 1,
        "last_tick_error": "notification_flush_failed",
    }
    assert "private flush backend secret" not in json.dumps(output)
    assert "private flush backend secret" not in json.dumps(status)


def test_flush_failure_tick_with_due_job_returns_only_normal_run_outcomes(
    tmp_path: Path,
) -> None:
    notifications = RecordingNotifications(fail_flush=True)
    scheduler, _, _, _ = make_scheduler(
        tmp_path,
        notifications=notifications,
        runtime=RuntimeSettings(
            enabled_jobs=("morning_briefing",),
            morning_time="08:00",
            grace_minutes=0,
        ),
    )

    output = scheduler.tick(datetime(2026, 7, 27, 8, 0, tzinfo=UTC))

    assert len(output) == 1
    assert output[0]["job"] == "morning_briefing"
    assert set(output[0]) == {
        "id",
        "job",
        "trigger",
        "local_date",
        "status",
        "started_at",
        "completed_at",
        "error_code",
        "notification_id",
        "degradations",
        "result",
    }
