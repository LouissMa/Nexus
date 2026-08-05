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
    assert json.loads(config_path.read_text(encoding="utf-8"))["runtime"][
        "enabled_jobs"
    ] == [
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
def test_runtime_requires_exact_boolean_switches(
    field_name: str, value: object
) -> None:
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
def test_runtime_accepts_http_webhook_urls_without_credentials(
    webhook_url: str,
) -> None:
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
        json.dumps(
            {**unrelated, "profile": {"display_name": "Old", "timezone": "UTC"}}
        ),
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


def _concurrent_profile_update(path: str, barrier: object, index: int) -> None:
    from nexus.config import update_profile_settings

    barrier.wait()
    update_profile_settings(f"User-{index}", "UTC", path=Path(path))


def _concurrent_runtime_update(path: str, barrier: object) -> None:
    from nexus.config import update_runtime_settings

    barrier.wait()
    update_runtime_settings(
        enabled_jobs=("morning_briefing",),
        morning_time="07:00",
        path=Path(path),
    )


def test_profile_and_runtime_updates_are_interprocess_transactional(
    tmp_path: Path,
) -> None:
    from multiprocessing import get_context

    config_path = tmp_path / "config.local.json"
    context = get_context("spawn")
    barrier = context.Barrier(8)
    processes = [
        context.Process(
            target=_concurrent_profile_update,
            args=(str(config_path), barrier, index),
        )
        for index in range(7)
    ]
    processes.append(
        context.Process(
            target=_concurrent_runtime_update,
            args=(str(config_path), barrier),
        )
    )

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0

    profile, runtime = load_runtime_settings(path=config_path)
    assert profile.display_name.startswith("User-")
    assert profile.timezone == "UTC"
    assert runtime.enabled_jobs == ("morning_briefing",)
    assert runtime.morning_time == "07:00"


def test_atomic_replacement_failure_preserves_original_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nexus.config as config_module

    config_path = tmp_path / "config.local.json"
    original = b'{"llm":{"provider":"custom"}}\n'
    config_path.write_bytes(original)

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("replacement interrupted")

    monkeypatch.setattr(config_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replacement interrupted"):
        config_module.save_local_config(
            {"llm": {"provider": "deepseek"}}, path=config_path
        )

    assert config_path.read_bytes() == original
    assert list(tmp_path.glob(".*.tmp")) == []


def _partial_runtime_worker(
    path: str,
    barrier: object,
    changes: dict[str, object],
) -> None:
    from nexus.config import patch_runtime_settings

    barrier.wait()
    patch_runtime_settings(changes, path=Path(path))


def _partial_profile_worker(
    path: str,
    barrier: object,
    changes: dict[str, object],
) -> None:
    from nexus.config import patch_profile_settings

    barrier.wait()
    patch_profile_settings(changes, path=Path(path))


def _hold_profile_transaction(
    path: str,
    entered: object,
    release: object,
) -> None:
    from nexus.config import mutate_local_config

    def mutation(config: dict[str, object]) -> None:
        entered.set()
        assert release.wait(timeout=20)
        config["profile"] = {"display_name": "Concurrent", "timezone": "UTC"}

    mutate_local_config(mutation, path=Path(path))


def _legacy_llm_update_with_save_probe(
    path: str,
    reached_save: object,
    release: object,
) -> None:
    import nexus.config as config_module

    original_save = config_module.save_local_config

    def probed_save(config: dict[str, object], path: Path | None = None) -> Path:
        reached_save.set()
        assert release.wait(timeout=20)
        return original_save(config, path)

    config_module.save_local_config = probed_save
    config_module.update_llm_settings(
        provider="deepseek",
        api_key="sk-concurrent-secret-value",
        path=Path(path),
    )


def test_concurrent_partial_runtime_updates_merge_distinct_fields(
    tmp_path: Path,
) -> None:
    from multiprocessing import get_context

    config_path = tmp_path / "config.local.json"
    context = get_context("spawn")
    barrier = context.Barrier(2)
    processes = [
        context.Process(
            target=_partial_runtime_worker,
            args=(str(config_path), barrier, {"morning_time": "06:45"}),
        ),
        context.Process(
            target=_partial_runtime_worker,
            args=(str(config_path), barrier, {"grace_minutes": 55}),
        ),
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0

    _profile, runtime = load_runtime_settings(path=config_path)
    assert runtime.morning_time == "06:45"
    assert runtime.grace_minutes == 55


def test_concurrent_partial_profile_updates_merge_distinct_fields(
    tmp_path: Path,
) -> None:
    from multiprocessing import get_context

    config_path = tmp_path / "config.local.json"
    context = get_context("spawn")
    barrier = context.Barrier(2)
    processes = [
        context.Process(
            target=_partial_profile_worker,
            args=(str(config_path), barrier, {"display_name": "Ada"}),
        ),
        context.Process(
            target=_partial_profile_worker,
            args=(str(config_path), barrier, {"timezone": "Asia/Shanghai"}),
        ),
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0

    profile, _runtime = load_runtime_settings(path=config_path)
    assert profile.display_name == "Ada"
    assert profile.timezone == "Asia/Shanghai"


def test_concurrent_llm_writer_preserves_transactional_profile_section(
    tmp_path: Path,
) -> None:
    from multiprocessing import get_context

    config_path = tmp_path / "config.local.json"
    context = get_context("spawn")
    entered = context.Event()
    release = context.Event()
    reached_save = context.Event()
    holder = context.Process(
        target=_hold_profile_transaction,
        args=(str(config_path), entered, release),
    )
    writer = context.Process(
        target=_legacy_llm_update_with_save_probe,
        args=(str(config_path), reached_save, release),
    )

    holder.start()
    assert entered.wait(timeout=10)
    writer.start()
    reached_save.wait(timeout=1.5)
    release.set()
    holder.join(timeout=30)
    writer.join(timeout=30)
    assert holder.exitcode == 0
    assert writer.exitcode == 0

    stored = json.loads(config_path.read_text(encoding="utf-8"))
    assert stored["profile"] == {
        "display_name": "Concurrent",
        "timezone": "UTC",
    }
    assert stored["llm"]["provider"] == "deepseek"
    assert stored["llm"]["api_key"] == "sk-concurrent-secret-value"


def test_partial_patch_validation_failure_preserves_original(tmp_path: Path) -> None:
    from nexus.config import patch_runtime_settings

    config_path = tmp_path / "config.local.json"
    update_runtime_settings(morning_time="07:30", path=config_path)
    before = config_path.read_bytes()

    with pytest.raises(ValueError, match="HH:MM"):
        patch_runtime_settings({"evening_time": "invalid"}, path=config_path)

    assert config_path.read_bytes() == before
