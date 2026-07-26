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
    check: bool = True,
) -> tuple[int, dict]:
    result = subprocess.run(
        [sys.executable, "-m", "nexus.cli", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result.returncode, json.loads(result.stdout)


def test_cli_agent_plan_review_and_briefing_workflows(tmp_path: Path) -> None:
    env = build_env(tmp_path)
    run_cli(
        "goal",
        "add",
        "Finish Phase 8",
        "--description",
        "Implement agent orchestration",
        env=env,
    )
    run_cli(
        "memory",
        "add",
        "Nexus multi-agent architecture",
        "--tags",
        "nexus",
        "agents",
        env=env,
    )

    _, plan = run_cli(
        "plan",
        "day",
        "--agents",
        "--now",
        "2026-07-26T08:00:00+00:00",
        env=env,
    )
    _, review = run_cli(
        "review",
        "day",
        "--agents",
        "--now",
        "2026-07-26T20:00:00+00:00",
        env=env,
    )
    _, briefing = run_cli(
        "briefing",
        "--agents",
        "--now",
        "2026-07-26T08:00:00+00:00",
        env=env,
    )

    assert plan["agents"]["used"] is True
    assert [step["agent"] for step in plan["agents"]["steps"]] == [
        "memory",
        "tool",
        "planner",
        "coach",
    ]
    assert [step["agent"] for step in review["agents"]["steps"]] == [
        "memory",
        "reflection",
        "coach",
    ]
    assert briefing["agents"]["used"] is True


def test_cli_lists_and_shows_agent_runs(tmp_path: Path) -> None:
    env = build_env(tmp_path)
    _, plan = run_cli("plan", "day", "--agents", env=env)
    run_id = plan["agents"]["run_id"]

    _, runs = run_cli("agent", "runs", "--limit", "1", env=env)
    _, shown = run_cli("agent", "show", run_id, env=env)

    assert runs["runs"][0]["run_id"] == run_id
    assert shown["run"]["run_id"] == run_id
    assert "artifacts" not in json.dumps(shown)


def test_cli_unknown_agent_run_returns_nonzero(tmp_path: Path) -> None:
    code, output = run_cli(
        "agent",
        "show",
        "missing",
        env=build_env(tmp_path),
        check=False,
    )

    assert code == 1
    assert output == {
        "status": "error",
        "error": "Agent run 'missing' not found.",
    }


def test_cli_default_workflows_remain_non_agent(tmp_path: Path) -> None:
    env = build_env(tmp_path)
    _, plan = run_cli("plan", "day", env=env)
    _, review = run_cli("review", "day", env=env)
    _, briefing = run_cli("briefing", env=env)

    assert "agents" not in plan
    assert "agents" not in review
    assert "agents" not in briefing


def build_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["NEXUS_HOME"] = str(tmp_path / "nexus-home")
    return env
