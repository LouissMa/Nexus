from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, env: dict[str, str]) -> dict:
    command = [sys.executable, "-m", "nexus.cli", *args]
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_memory_goal_and_review_flow(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["NEXUS_HOME"] = str(tmp_path / "nexus-home")

    memory = run_cli("memory", "add", "User wants to practice English daily", "--tags", "learning", env=env)
    assert memory["status"] == "ok"

    goal = run_cli("goal", "add", "Practice English", "--description", "15 minutes speaking", "--cadence-days", "1", env=env)
    goal_id = goal["goal"]["id"]

    search = run_cli("memory", "search", "English", env=env)
    assert len(search["results"]) == 1

    review = run_cli("review", "--now", "2030-01-03T00:00:00+00:00", env=env)
    assert any(goal_id in reminder for reminder in review["reminders"])

    briefing = run_cli(
        "briefing",
        "--name",
        "Louis",
        "--weather",
        "weather is sunny, high 25 C",
        "--now",
        "2030-01-03T08:00:00+00:00",
        env=env,
    )
    assert briefing["user_name"] == "Louis"
    assert briefing["today"]["date"] == "1月3日"
    assert briefing["important_goals"][0]["id"] == goal_id
    assert "Practice English" in briefing["briefing"]
    assert "Louis" in briefing["briefing"]

    check_in = run_cli("goal", "check-in", goal_id, "Completed today's session", env=env)
    assert check_in["status"] == "ok"
