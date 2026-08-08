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


def env_for(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["NEXUS_HOME"] = str(tmp_path / "nexus-home")
    return env


def test_project_cli_workflow(tmp_path: Path) -> None:
    env = env_for(tmp_path)
    created = run_cli(
        "project",
        "add",
        "Nexus",
        "--description",
        "Adaptive workspace",
        "--priority",
        "1",
        "--target-date",
        "2026-08-30",
        "--goal-id",
        "goal-a",
        env=env,
    )
    project_id = created["project"]["id"]

    milestone = run_cli(
        "project",
        "milestone-add",
        project_id,
        "Dashboard",
        "--target-date",
        "2026-08-20",
        env=env,
    )
    milestone_id = milestone["milestone"]["id"]
    completed = run_cli(
        "project",
        "milestone-update",
        project_id,
        milestone_id,
        "--status",
        "completed",
        env=env,
    )
    assert completed["project"]["summary"]["progress_percent"] == 100

    listed = run_cli("project", "list", env=env)
    assert listed["projects"][0]["name"] == "Nexus"

    archived = run_cli("project", "archive", project_id, env=env)
    assert archived["project"]["status"] == "archived"


def test_project_cli_progress_correction_and_validation(tmp_path: Path) -> None:
    env = env_for(tmp_path)
    created = run_cli("project", "add", "Research", env=env)
    project_id = created["project"]["id"]
    run_cli("project", "progress", project_id, "70", env=env)

    rejected = run_cli(
        "project",
        "progress",
        project_id,
        "20",
        env=env,
        expected_code=2,
    )
    assert rejected["code"] == "invalid_project"

    corrected = run_cli(
        "project",
        "progress",
        project_id,
        "20",
        "--correction",
        "--note",
        "Scope changed",
        env=env,
    )
    assert corrected["project"]["summary"]["progress_percent"] == 20
