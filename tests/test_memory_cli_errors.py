from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, env: dict[str, str]) -> tuple[int, dict]:
    result = subprocess.run(
        [sys.executable, "-m", "nexus.cli", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, json.loads(result.stdout)


def build_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["NEXUS_HOME"] = str(tmp_path / "nexus-home")
    return env


def test_cli_rejects_invalid_importance_and_timestamp(tmp_path: Path) -> None:
    env = build_env(tmp_path)

    importance_code, importance = run_cli(
        "memory",
        "add",
        "Invalid score",
        "--importance",
        "1.5",
        env=env,
    )
    timestamp_code, timestamp = run_cli(
        "memory",
        "add",
        "Invalid expiry",
        "--expires-at",
        "not-a-date",
        env=env,
    )

    assert importance_code == 2
    assert "importance" in importance["error"]
    assert timestamp_code == 2
    assert "ISO timestamp" in timestamp["error"]


def test_cli_rejects_self_relation_and_forgotten_archive(tmp_path: Path) -> None:
    env = build_env(tmp_path)
    _, added = run_cli("memory", "add", "One fact", env=env)
    memory_id = added["memory"]["id"]

    relation_code, relation = run_cli(
        "memory",
        "relate",
        memory_id,
        "--conflicts-with",
        memory_id,
        env=env,
    )
    run_cli("memory", "forget", memory_id, env=env)
    archive_code, archive = run_cli("memory", "archive", memory_id, env=env)

    assert relation_code == 2
    assert "itself" in relation["error"]
    assert archive_code == 2
    assert "forgotten" in archive["error"]
