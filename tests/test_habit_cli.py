from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, env: dict[str, str], expected_code: int = 0) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "nexus.cli", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == expected_code, result.stderr or result.stdout
    return json.loads(result.stdout)


def isolated_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["NEXUS_HOME"] = str(tmp_path / "nexus-home")
    return env


def test_habit_cli_add_list_check_in_and_archive(tmp_path: Path) -> None:
    env = isolated_env(tmp_path)
    created = run_cli(
        "habit",
        "add",
        "Read papers",
        "--description",
        "One focused paper",
        "--cadence",
        "daily",
        "--target-count",
        "2",
        env=env,
    )
    habit_id = created["habit"]["id"]

    listed = run_cli("habit", "list", "--now", "2026-08-08T08:00:00+00:00", env=env)
    assert listed["habits"][0]["name"] == "Read papers"

    checked = run_cli(
        "habit",
        "check-in",
        habit_id,
        "--date",
        "2026-08-08",
        "--count",
        "2",
        "--note",
        "Completed",
        "--now",
        "2026-08-08T08:00:00+00:00",
        env=env,
    )
    assert checked["habit"]["summary"]["today_complete"] is True

    archived = run_cli("habit", "archive", habit_id, env=env)
    assert archived["habit"]["status"] == "archived"
    assert run_cli("habit", "list", env=env)["habits"] == []
    assert len(run_cli("habit", "list", "--include-archived", env=env)["habits"]) == 1


def test_habit_cli_rejects_invalid_weekday_config(tmp_path: Path) -> None:
    env = isolated_env(tmp_path)

    payload = run_cli(
        "habit",
        "add",
        "Read",
        "--cadence",
        "weekdays",
        env=env,
        expected_code=2,
    )

    assert payload["status"] == "error"
    assert payload["code"] == "invalid_habit"
