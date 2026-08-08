from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from nexus.store import JsonStore


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


def test_replan_preview_and_apply_cli(tmp_path: Path) -> None:
    home = tmp_path / "home"
    store = JsonStore(home / "state.json")
    state = store.load()
    state["daily_tasks"] = [
        {
            "id": "t1",
            "title": "Research",
            "plan_date": "2026-08-08",
            "priority": 1,
            "estimated_minutes": 60,
            "status": "pending",
            "blocker": None,
        }
    ]
    store.save(state)
    preview_result = run_cli(
        home,
        "replan",
        "preview",
        "--date",
        "2026-08-08",
        "--events-json",
        "[]",
        "--working-start",
        "09:00",
        "--working-end",
        "17:00",
        "--now",
        "2026-08-08T08:00:00+00:00",
    )
    preview = json.loads(preview_result.stdout)["preview"]
    applied = run_cli(
        home,
        "replan",
        "apply",
        "--preview-json",
        json.dumps(preview),
        "--events-json",
        "[]",
        "--now",
        "2026-08-08T08:00:00+00:00",
    )
    assert json.loads(applied.stdout)["result"]["updated_task_ids"] == ["t1"]
