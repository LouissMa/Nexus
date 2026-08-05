from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cli(
    *args: str,
    env: dict[str, str],
    expected_code: int = 0,
) -> tuple[dict[str, object], subprocess.CompletedProcess[str]]:
    result = subprocess.run(
        [sys.executable, "-m", "nexus.cli", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == expected_code, result.stderr or result.stdout
    return json.loads(result.stdout), result


def isolated_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["NEXUS_HOME"] = str(tmp_path / "nexus-home")
    env.pop("NEXUS_LLM_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)
    return env


def test_profile_commands_persist_and_merge_omitted_fields(tmp_path: Path) -> None:
    env = isolated_env(tmp_path)

    saved, _ = run_cli(
        "config",
        "profile",
        "set",
        "--name",
        "Louis",
        "--timezone",
        "Asia/Shanghai",
        env=env,
    )
    assert saved["status"] == "ok"
    assert saved["profile"] == {
        "display_name": "Louis",
        "timezone": "Asia/Shanghai",
    }

    merged, _ = run_cli("config", "profile", "set", "--name", "Ada", env=env)
    assert merged["profile"] == {
        "display_name": "Ada",
        "timezone": "Asia/Shanghai",
    }
    shown, _ = run_cli("config", "profile", "show", env=env)
    assert shown["profile"] == merged["profile"]


def test_runtime_config_masks_webhook_merges_and_rejects_conflicts_atomically(
    tmp_path: Path,
) -> None:
    env = isolated_env(tmp_path)
    saved, result = run_cli(
        "config",
        "runtime",
        "set",
        "--job",
        "morning_briefing",
        "--job",
        "evening_review",
        "--morning-time",
        "07:30",
        "--quiet-hours",
        "23:00",
        "07:00",
        "--webhook-url",
        "https://hooks.example.test/private-token",
        "--console",
        "--use-llm",
        "--no-live-tools",
        "--agents",
        "--coach-mode",
        "academic",
        env=env,
    )
    assert saved["status"] == "ok"
    runtime = saved["runtime"]
    assert runtime["enabled_jobs"] == ["morning_briefing", "evening_review"]
    assert runtime["webhook_url"] == "***configured***"
    assert runtime["console_enabled"] is True
    assert runtime["use_llm"] is True
    assert runtime["live_tools"] is False
    assert "private-token" not in result.stdout

    merged, _ = run_cli("config", "runtime", "set", "--grace-minutes", "45", env=env)
    assert merged["runtime"]["enabled_jobs"] == runtime["enabled_jobs"]
    assert merged["runtime"]["quiet_hours_start"] == "23:00"
    assert merged["runtime"]["webhook_url"] == "***configured***"

    config_path = Path(env["NEXUS_HOME"]) / "config.local.json"
    before = config_path.read_bytes()
    error, result = run_cli(
        "config",
        "runtime",
        "set",
        "--webhook-url",
        "https://new.example.test/hook",
        "--clear-webhook",
        env=env,
        expected_code=2,
    )
    assert error["status"] == "error"
    assert error["code"] == "invalid_runtime_config"
    assert config_path.read_bytes() == before
    assert "new.example.test" not in result.stdout


def test_runtime_jobs_notifications_and_bounded_start(tmp_path: Path) -> None:
    env = isolated_env(tmp_path)
    run_cli(
        "config",
        "profile",
        "set",
        "--name",
        "Louis",
        "--timezone",
        "UTC",
        env=env,
    )
    run_cli(
        "config",
        "runtime",
        "set",
        "--job",
        "morning_briefing",
        "--poll-interval-seconds",
        "1",
        env=env,
    )

    status, result = run_cli("runtime", "status", env=env)
    assert status["status"] == "ok"
    assert status["scheduler"]["runtime"]["enabled_jobs"] == ["morning_briefing"]
    assert "hooks.example" not in result.stdout.lower()

    ticked, _ = run_cli("runtime", "tick", env=env)
    assert ticked["status"] == "ok"
    assert isinstance(ticked["outcomes"], list)

    manual, _ = run_cli("runtime", "run", "morning_briefing", env=env)
    assert manual["status"] == "ok"
    assert manual["result"]["job"] == "morning_briefing"

    listed, _ = run_cli("notifications", "list", "--limit", "5", env=env)
    assert listed["notifications"]
    flushed, _ = run_cli("notifications", "flush", env=env)
    assert flushed["status"] == "ok"
    assert isinstance(flushed["notifications"], list)

    started, _ = run_cli("runtime", "start", "--max-ticks", "1", env=env)
    assert started == {"status": "ok", "result": {"ticks": 1, "errors": 0}}


def test_runtime_invalid_config_is_lazy_and_run_requires_job(tmp_path: Path) -> None:
    env = isolated_env(tmp_path)
    home = Path(env["NEXUS_HOME"])
    home.mkdir(parents=True)
    (home / "config.local.json").write_text(
        json.dumps({"runtime": {"morning_time": "invalid"}}),
        encoding="utf-8",
    )

    legacy, _ = run_cli("goal", "list", env=env)
    assert legacy == {"goals": []}

    error, _ = run_cli("runtime", "status", env=env, expected_code=2)
    assert error["status"] == "error"
    assert error["code"] == "invalid_runtime_config"

    result = subprocess.run(
        [sys.executable, "-m", "nexus.cli", "runtime", "run"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "required" in result.stderr.lower()


def test_runtime_start_keyboard_interrupt_emits_stopped_json(
    monkeypatch,
    capsys,
) -> None:
    from nexus import cli

    class InterruptingScheduler:
        def run_forever(self, *, max_ticks=None):
            assert max_ticks is None
            raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_build_scheduler", lambda: InterruptingScheduler())
    monkeypatch.setattr(sys, "argv", ["nexus", "runtime", "start"])

    cli.main()

    assert json.loads(capsys.readouterr().out) == {
        "status": "stopped",
        "result": {"reason": "keyboard_interrupt"},
    }


def test_empty_webhook_value_conflicts_with_clear_without_persisting(
    tmp_path: Path,
) -> None:
    env = isolated_env(tmp_path)
    run_cli(
        "config",
        "runtime",
        "set",
        "--webhook-url",
        "https://hooks.example.test/original",
        env=env,
    )
    config_path = Path(env["NEXUS_HOME"]) / "config.local.json"
    before = config_path.read_bytes()

    error, _ = run_cli(
        "config",
        "runtime",
        "set",
        "--webhook-url",
        "",
        "--clear-webhook",
        env=env,
        expected_code=2,
    )

    assert error["code"] == "invalid_runtime_config"
    assert config_path.read_bytes() == before


def test_profile_and_runtime_set_submit_only_explicit_patches(
    monkeypatch,
    capsys,
) -> None:
    from nexus import cli
    from nexus.runtime_config import ProfileSettings, RuntimeSettings

    calls: list[tuple[str, dict[str, object]]] = []

    def reject_preload():
        raise AssertionError("set commands must not preload current settings")

    def patch_profile(changes):
        calls.append(("profile", changes))
        return ProfileSettings(display_name="Ada", timezone="UTC"), Path("config.json")

    def patch_runtime(changes):
        calls.append(("runtime", changes))
        return RuntimeSettings(grace_minutes=45), Path("config.json")

    monkeypatch.setattr(cli, "load_runtime_settings", reject_preload)
    monkeypatch.setattr(cli, "patch_profile_settings", patch_profile)
    monkeypatch.setattr(cli, "patch_runtime_settings", patch_runtime)

    monkeypatch.setattr(
        sys,
        "argv",
        ["nexus", "config", "profile", "set", "--name", "Ada"],
    )
    cli.main()
    json.loads(capsys.readouterr().out)

    monkeypatch.setattr(
        sys,
        "argv",
        ["nexus", "config", "runtime", "set", "--grace-minutes", "45"],
    )
    cli.main()
    json.loads(capsys.readouterr().out)

    assert calls == [
        ("profile", {"display_name": "Ada"}),
        ("runtime", {"grace_minutes": 45}),
    ]
