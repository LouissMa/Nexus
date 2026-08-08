from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from nexus import cli


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
    return env


def test_dashboard_snapshot_is_privacy_safe(tmp_path: Path) -> None:
    env = isolated_env(tmp_path)
    home = Path(env["NEXUS_HOME"])
    home.mkdir(parents=True)
    secret = "sk-dashboard-secret-value"
    (home / "config.local.json").write_text(
        json.dumps(
            {
                "profile": {"display_name": "Louis", "timezone": "UTC"},
                "llm": {"provider": "deepseek", "api_key": secret},
                "runtime": {
                    "webhook_url": "https://hooks.example.test/private",
                },
            }
        ),
        encoding="utf-8",
    )

    snapshot, result = run_cli("dashboard", "snapshot", env=env)
    assert set(snapshot["sections"]) == {
        "today",
        "goals",
        "habits",
        "projects",
        "suggestions",
        "memory",
        "activity",
        "settings",
    }
    assert secret not in result.stdout
    assert "hooks.example.test" not in result.stdout


def test_dashboard_rejects_unsafe_bind_with_exit_two(tmp_path: Path) -> None:
    env = isolated_env(tmp_path)
    error, _ = run_cli(
        "dashboard",
        "serve",
        "--host",
        "0.0.0.0",
        env=env,
        expected_code=2,
    )
    assert error == {
        "status": "error",
        "code": "unsafe_dashboard_bind",
        "error": "Dashboard host must be a loopback address.",
    }


def test_dashboard_serve_prints_url_and_shuts_down_on_interrupt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[str] = []

    class FakeServer:
        url = "http://127.0.0.1:43210"

        def start(self) -> None:
            events.append("start")

        @property
        def is_running(self) -> bool:
            events.append("wait")
            raise KeyboardInterrupt

        def shutdown(self) -> None:
            events.append("shutdown")

    monkeypatch.setattr(cli, "_build_dashboard_server", lambda **_kwargs: FakeServer())
    monkeypatch.setattr(sys, "argv", ["nexus", "dashboard", "serve", "--port", "0"])

    cli.main()

    output = json.loads(capsys.readouterr().out)
    assert output == {"status": "serving", "url": FakeServer.url}
    assert events == ["start", "wait", "shutdown"]


def test_dashboard_snapshot_isolates_malformed_optional_automation_config(
    tmp_path: Path,
) -> None:
    env = isolated_env(tmp_path)
    home = Path(env["NEXUS_HOME"])
    home.mkdir(parents=True)
    (home / "config.local.json").write_text(
        json.dumps(
            {
                "profile": {"display_name": "Louis", "timezone": "UTC"},
                "automations": {"broken": {"type": "browser"}},
            }
        ),
        encoding="utf-8",
    )

    snapshot, _ = run_cli("dashboard", "snapshot", env=env)

    sections = snapshot["sections"]
    assert sections["today"]["status"] == "ok"
    assert sections["goals"]["status"] == "ok"
    assert sections["memory"]["status"] == "ok"
    assert sections["activity"]["status"] == "error"
    assert sections["settings"]["status"] == "error"


def test_dashboard_startup_failure_prints_one_error_and_shuts_down(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[str] = []

    class FailingServer:
        url = "http://127.0.0.1:43210"

        def start(self) -> None:
            events.append("start")
            raise RuntimeError("bind failed")

        def shutdown(self) -> None:
            events.append("shutdown")

    monkeypatch.setattr(
        cli, "_build_dashboard_server", lambda **_kwargs: FailingServer()
    )
    monkeypatch.setattr(sys, "argv", ["nexus", "dashboard", "serve", "--port", "0"])

    with pytest.raises(SystemExit) as stopped:
        cli.main()

    assert stopped.value.code == 1
    output = capsys.readouterr().out
    assert json.loads(output) == {
        "status": "error",
        "code": "dashboard_failed",
        "error": "Dashboard operation failed.",
    }
    assert output.count("{") == 1
    assert events == ["start", "shutdown"]
