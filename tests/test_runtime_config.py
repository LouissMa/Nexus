from __future__ import annotations

import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from nexus.config import (
    load_runtime_settings,
    update_profile_settings,
    update_runtime_settings,
)
from nexus.runtime_config import ProfileSettings, RuntimeSettings


def test_runtime_settings_default_to_safe_local_configuration() -> None:
    profile = ProfileSettings()
    runtime = RuntimeSettings()

    assert profile.display_name == "User"
    assert ZoneInfo(profile.timezone).key == profile.timezone
    assert runtime.enabled_jobs == ()
    assert runtime.morning_time == "08:00"
    assert runtime.evening_time == "20:00"
    assert runtime.reminder_time == "12:00"
    assert runtime.inbox_enabled is True
    assert runtime.console_enabled is False
    assert runtime.webhook_url is None
    assert runtime.use_llm is False
    assert runtime.live_tools is False
    assert runtime.agents is False
    assert runtime.coach_mode == "gentle"


def test_profile_requires_an_iana_timezone() -> None:
    profile = ProfileSettings(display_name="Ava", timezone="Asia/Shanghai")

    assert profile.timezone == "Asia/Shanghai"

    with pytest.raises(ValueError, match="IANA"):
        ProfileSettings(timezone="China Standard Time")


@pytest.mark.parametrize("value", ["8:00", "24:00", "08:60", "noon"])
def test_runtime_rejects_invalid_clock_times(value: str) -> None:
    with pytest.raises(ValueError, match="HH:MM"):
        RuntimeSettings(morning_time=value)


def test_runtime_accepts_overnight_quiet_hours() -> None:
    runtime = RuntimeSettings(quiet_hours_start="22:00", quiet_hours_end="07:00")

    assert runtime.quiet_hours_start == "22:00"
    assert runtime.quiet_hours_end == "07:00"

    with pytest.raises(ValueError, match="different"):
        RuntimeSettings(quiet_hours_start="22:00", quiet_hours_end="22:00")


def test_runtime_rejects_incomplete_quiet_hours() -> None:
    with pytest.raises(ValueError, match="both"):
        RuntimeSettings(quiet_hours_start="22:00")


def test_runtime_persists_enabled_job_configuration(tmp_path: Path) -> None:
    config_path = tmp_path / "config.local.json"
    update_profile_settings("Ava", "Asia/Shanghai", path=config_path)
    saved, saved_path = update_runtime_settings(
        enabled_jobs=("morning_briefing", "stale_goal_reminders"),
        morning_time="07:15",
        reminder_time="09:30",
        grace_minutes=45,
        poll_interval_seconds=30,
        path=config_path,
    )

    profile, loaded = load_runtime_settings(path=config_path)

    assert saved_path == config_path
    assert saved.enabled_jobs == ("morning_briefing", "stale_goal_reminders")
    assert profile == ProfileSettings(display_name="Ava", timezone="Asia/Shanghai")
    assert loaded == saved
    assert json.loads(config_path.read_text(encoding="utf-8"))["runtime"]["enabled_jobs"] == [
        "morning_briefing",
        "stale_goal_reminders",
    ]


def test_runtime_rejects_unknown_job_names() -> None:
    with pytest.raises(ValueError, match="Unknown runtime job"):
        RuntimeSettings(enabled_jobs=("morning_briefing", "nightly_cleanup"))


def test_runtime_accepts_job_name_lists_and_normalizes_to_tuple() -> None:
    runtime = RuntimeSettings(enabled_jobs=["morning_briefing", "evening_review"])

    assert runtime.enabled_jobs == ("morning_briefing", "evening_review")


@pytest.mark.parametrize(
    "enabled_jobs",
    [
        "morning_briefing",
        {"morning_briefing": True},
        {"morning_briefing"},
        iter(["morning_briefing"]),
        ["morning_briefing", 42],
    ],
)
def test_runtime_requires_a_sequence_of_job_name_strings(enabled_jobs: object) -> None:
    with pytest.raises(ValueError, match="enabled_jobs"):
        RuntimeSettings(enabled_jobs=enabled_jobs)


@pytest.mark.parametrize(
    "field_name",
    ["inbox_enabled", "console_enabled", "use_llm", "live_tools", "agents"],
)
@pytest.mark.parametrize("value", [0, 1, "true"])
def test_runtime_requires_exact_boolean_switches(field_name: str, value: object) -> None:
    with pytest.raises(ValueError, match=field_name):
        RuntimeSettings(**{field_name: value})


@pytest.mark.parametrize("field_name", ["grace_minutes", "poll_interval_seconds"])
@pytest.mark.parametrize("value", [False, True])
def test_runtime_rejects_booleans_for_integer_intervals(
    field_name: str,
    value: bool,
) -> None:
    with pytest.raises(ValueError, match=field_name):
        RuntimeSettings(**{field_name: value})


def test_runtime_rejects_unknown_coach_modes() -> None:
    with pytest.raises(ValueError, match="coach mode"):
        RuntimeSettings(coach_mode="uncompromising")


@pytest.mark.parametrize(
    "webhook_url",
    [
        "ftp://hooks.example.test/events",
        "https:///events",
        "https://ava@hooks.example.test/events",
        "https://ava:secret@hooks.example.test/events",
        "https://bad host.example.test/events",
        "https://hooks.example.test/bad path",
        "https://hooks.example.test/bad\tpath",
        "https://hooks.example.test/bad\npath",
        "https://hooks.example.test/bad\x00path",
        "https://hooks.example.test/bad\x7fpath",
    ],
)
def test_runtime_rejects_unsafe_webhook_urls(webhook_url: str) -> None:
    with pytest.raises(ValueError, match="webhook_url"):
        RuntimeSettings(webhook_url=webhook_url)


@pytest.mark.parametrize(
    "webhook_url",
    [
        "http://localhost:8080/events",
        "https://hooks.example.test/events",
    ],
)
def test_runtime_accepts_http_webhook_urls_without_credentials(webhook_url: str) -> None:
    assert RuntimeSettings(webhook_url=webhook_url).webhook_url == webhook_url


def test_runtime_persists_scheduled_workflow_switches(tmp_path: Path) -> None:
    config_path = tmp_path / "config.local.json"

    saved, _ = update_runtime_settings(
        use_llm=True,
        live_tools=True,
        agents=True,
        coach_mode="academic",
        path=config_path,
    )
    _, loaded = load_runtime_settings(path=config_path)

    assert loaded == saved
    assert loaded.use_llm is True
    assert loaded.live_tools is True
    assert loaded.agents is True
    assert loaded.coach_mode == "academic"
    stored = json.loads(config_path.read_text(encoding="utf-8"))["runtime"]
    assert stored["use_llm"] is True
    assert stored["live_tools"] is True
    assert stored["agents"] is True
    assert stored["coach_mode"] == "academic"


def test_valid_updates_preserve_unrelated_config_structure(tmp_path: Path) -> None:
    config_path = tmp_path / "config.local.json"
    unrelated = {
        "llm": {"provider": "custom", "models": ["small", "large"]},
        "tools": {"filesystem": {"enabled": True, "roots": ["D:/notes"]}},
        "extension": {"nested": {"values": [1, {"keep": None}]}},
    }
    config_path.write_text(
        json.dumps({**unrelated, "profile": {"display_name": "Old", "timezone": "UTC"}}),
        encoding="utf-8",
    )

    update_profile_settings("Ava", "Asia/Shanghai", path=config_path)
    update_runtime_settings(enabled_jobs=["morning_briefing"], path=config_path)

    stored = json.loads(config_path.read_text(encoding="utf-8"))
    assert {key: stored[key] for key in unrelated} == unrelated


def test_invalid_runtime_update_leaves_config_file_unchanged(tmp_path: Path) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        '{\n  "llm": {"provider": "custom"},\n  "runtime": {"enabled_jobs": []}\n}\n',
        encoding="utf-8",
    )
    before = config_path.read_bytes()

    with pytest.raises(ValueError, match="inbox_enabled"):
        update_runtime_settings(inbox_enabled=1, path=config_path)

    assert config_path.read_bytes() == before

def test_masked_serializers_do_not_expose_webhook_url() -> None:
    profile = ProfileSettings(display_name="Ava", timezone="Asia/Shanghai")
    runtime = RuntimeSettings(webhook_url="https://hooks.example.test/secret-token")

    shown = {"profile": profile.masked(), "runtime": runtime.masked()}

    assert shown["profile"] == {"display_name": "Ava", "timezone": "Asia/Shanghai"}
    assert shown["runtime"]["webhook_url"] == "***configured***"
    assert "https://hooks.example.test/secret-token" not in json.dumps(shown)
