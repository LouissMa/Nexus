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


def test_ask_cli_reads_and_approval_gates_mutation(tmp_path: Path) -> None:
    home = tmp_path / "home"
    goals = json.loads(
        run_cli(
            home, "ask", "show my goals", "--now", "2026-08-08T09:00:00+00:00"
        ).stdout
    )
    assert goals["intent"] == "list_goals"
    preview = json.loads(
        run_cli(
            home,
            "ask",
            "remember Nexus learns my goals",
            "--show-intent",
            "--now",
            "2026-08-08T09:00:00+00:00",
        ).stdout
    )
    assert preview["requires_approval"] is True
    assert preview["intent_details"]["source"] == "local"
    accepted = json.loads(
        run_cli(
            home,
            "ask",
            "remember Nexus learns my goals",
            "--approve",
            "--now",
            "2026-08-08T09:00:00+00:00",
        ).stdout
    )
    assert accepted["result"]["memory"]["text"] == "Nexus learns my goals"
