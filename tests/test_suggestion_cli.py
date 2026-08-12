from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def run_cli(
    home: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["NEXUS_HOME"] = str(home)
    result = subprocess.run(
        [sys.executable, "-m", "nexus.cli", *args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stderr)
    return result


def payload(result: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(result.stdout)


def test_suggestion_refresh_list_accept_and_dismiss(tmp_path: Path) -> None:
    home = tmp_path / "home"
    goal = payload(run_cli(home, "goal", "add", "Nexus", "--cadence-days", "1"))["goal"]
    refreshed = payload(
        run_cli(home, "suggestion", "refresh", "--now", "2030-08-08T09:00:00+00:00")
    )
    quiet = next(
        item for item in refreshed["suggestions"] if item["kind"] == "quiet_goal"
    )
    assert quiet["source_ids"] == [f"goal:{goal['id']}"]

    denied = run_cli(
        home,
        "suggestion",
        "accept",
        quiet["id"],
        "--now",
        "2030-08-08T09:00:00+00:00",
        check=False,
    )
    assert denied.returncode == 2
    accepted = payload(
        run_cli(
            home,
            "suggestion",
            "accept",
            quiet["id"],
            "--approve",
            "--now",
            "2030-08-08T09:00:00+00:00",
        )
    )
    assert accepted["suggestion"]["status"] == "accepted"

    listed = payload(
        run_cli(home, "suggestion", "list", "--now", "2030-08-08T10:00:00+00:00")
    )
    assert listed["suggestions"][0]["status"] == "accepted"


def test_suggestion_refresh_live_tools_degrades_when_calendar_is_disabled(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    run_cli(home, "goal", "add", "Nexus", "--cadence-days", "1")
    run_cli(home, "memory", "add", "Nexus needs a retrieval benchmark")

    result = payload(
        run_cli(
            home,
            "suggestion",
            "refresh",
            "--live-tools",
            "--now",
            "2030-08-08T09:00:00+00:00",
        )
    )

    assert result["suggestions"]
    assert result["context"]["calendar"] == "unavailable"
    assert result["context"]["rag"] == "available"
    assert result["context"]["degradations"] == ["calendar_unavailable"]
