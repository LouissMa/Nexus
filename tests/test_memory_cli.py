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
    payload = json.loads(result.stdout)
    if check:
        assert result.returncode == 0, result.stderr
    return result.returncode, payload


def build_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["NEXUS_HOME"] = str(tmp_path / "nexus-home")
    return env


def test_memory_cli_metadata_relations_and_lifecycle(tmp_path: Path) -> None:
    env = build_env(tmp_path)
    _, old = run_cli(
        "memory",
        "add",
        "My IELTS exam is in September",
        "--tags",
        "exam",
        "--importance",
        "0.9",
        "--privacy",
        "personal",
        "--pin",
        env=env,
    )
    _, new = run_cli(
        "memory",
        "add",
        "My IELTS exam is in October",
        "--tags",
        "exam",
        env=env,
    )
    old_id = old["memory"]["id"]
    new_id = new["memory"]["id"]

    _, shown = run_cli("memory", "show", old_id, env=env)
    assert shown["memory"]["importance"] == 0.9
    assert shown["memory"]["privacy"] == "personal"
    assert shown["memory"]["pinned"] is True

    _, updated = run_cli(
        "memory",
        "update",
        new_id,
        "--importance",
        "0.8",
        "--privacy",
        "shared",
        "--expires-at",
        "2027-01-01T00:00:00+00:00",
        "--pin",
        env=env,
    )
    assert updated["memory"]["pinned"] is True
    assert updated["memory"]["privacy"] == "shared"

    _, relation = run_cli("memory", "relate", new_id, "--supersedes", old_id, env=env)
    assert relation["relation"]["target"]["status"] == "archived"
    _, conflict = run_cli(
        "memory", "relate", new_id, "--conflicts-with", old_id, env=env
    )
    assert conflict["relation"]["memory"]["conflicts_with"] == [old_id]

    _, forgotten = run_cli("memory", "forget", new_id, env=env)
    assert forgotten["memory"]["status"] == "forgotten"
    code, refused = run_cli("memory", "purge", new_id, env=env, check=False)
    assert code == 2
    assert "confirmation" in refused["error"]
    _, purged = run_cli("memory", "purge", new_id, "--confirm", env=env)
    assert purged["result"]["purged"] is True


def test_memory_cli_compression_maintenance_and_privacy_retrieval(
    tmp_path: Path,
) -> None:
    env = build_env(tmp_path)
    _, first = run_cli(
        "memory",
        "add",
        "Read old paper A",
        "--tags",
        "research",
        "--importance",
        "0.2",
        env=env,
    )
    _, second = run_cli(
        "memory",
        "add",
        "Read old paper B",
        "--tags",
        "research",
        "--importance",
        "0.3",
        env=env,
    )
    _, shared = run_cli(
        "memory",
        "add",
        "Nexus shared architecture",
        "--privacy",
        "shared",
        env=env,
    )

    state_path = Path(env["NEXUS_HOME"]) / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    for item in state["memories"]:
        if item["id"] in {first["memory"]["id"], second["memory"]["id"]}:
            item["created_at"] = "2026-01-01T00:00:00+00:00"
        if item["id"] == shared["memory"]["id"]:
            item["expires_at"] = "2026-07-26T00:00:00+00:00"
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    _, preview = run_cli(
        "memory",
        "compress",
        "--older-than-days",
        "90",
        "--max-importance",
        "0.4",
        "--dry-run",
        "--now",
        "2026-07-27T08:00:00+00:00",
        env=env,
    )
    assert len(preview["compression"]["groups"]) == 1
    _, applied = run_cli(
        "memory",
        "compress",
        "--older-than-days",
        "90",
        "--max-importance",
        "0.4",
        "--now",
        "2026-07-27T08:00:00+00:00",
        env=env,
    )
    assert len(applied["compression"]["created"]) == 1

    _, maintenance = run_cli(
        "memory",
        "maintain",
        "--dry-run",
        "--now",
        "2026-07-27T08:00:00+00:00",
        env=env,
    )
    assert maintenance["maintenance"]["expired_ids"] == [shared["memory"]["id"]]

    _, shared_results = run_cli(
        "memory",
        "retrieve",
        "Nexus architecture",
        "--privacy",
        "shared",
        "--now",
        "2026-07-25T08:00:00+00:00",
        env=env,
    )
    assert [item["id"] for item in shared_results["results"]] == [
        shared["memory"]["id"]
    ]
