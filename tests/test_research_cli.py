from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def env_for(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["NEXUS_HOME"] = str(tmp_path / "nexus-home")
    return env


def run_cli(*args: str, env: dict[str, str], code: int = 0) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "nexus.cli", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == code, result.stderr or result.stdout
    return json.loads(result.stdout)


def test_research_cli_workflow(tmp_path: Path) -> None:
    env = env_for(tmp_path)
    created = run_cli(
        "research",
        "create",
        "RAG evaluation",
        "--objective",
        "Compare dense and hybrid retrieval.",
        "--question",
        "What improves recall?",
        env=env,
    )
    project_id = created["research"]["id"]
    source = run_cli(
        "research",
        "source-add",
        project_id,
        "--type",
        "paper",
        "--title",
        "Hybrid retrieval study",
        "--locator",
        "https://doi.org/10.1000/example",
        "--note",
        "Hybrid fusion improved recall.",
        env=env,
    )["source"]
    run_cli(
        "research",
        "note-add",
        project_id,
        "The gain was two relevant memories.",
        "--source-id",
        source["id"],
        "--tag",
        "evaluation",
        env=env,
    )
    run_cli(
        "research",
        "experiment-add",
        project_id,
        "Dense versus hybrid",
        "--hypothesis",
        "Hybrid improves recall.",
        "--method",
        "Compare twenty queries.",
        "--result",
        "Hybrid recovered two additional memories.",
        "--status",
        "completed",
        "--source-id",
        source["id"],
        env=env,
    )

    synthesis = run_cli("research", "synthesize", project_id, env=env)
    answer = run_cli(
        "research",
        "ask",
        project_id,
        "Did hybrid retrieval improve recall?",
        env=env,
    )
    listed = run_cli("research", "list", env=env)

    assert synthesis["synthesis"]["current_findings"]
    assert answer["answer"]["references"]
    assert listed["research"][0]["summary"]["experiment_count"] == 1


def test_research_cli_investigate_without_live_tools_and_errors(tmp_path: Path) -> None:
    env = env_for(tmp_path)
    project_id = run_cli("research", "create", "Offline", env=env)["research"]["id"]

    investigation = run_cli(
        "research", "investigate", project_id, "offline retrieval", env=env
    )
    live_degraded = run_cli(
        "research",
        "investigate",
        project_id,
        "permissioned literature",
        "--live-tools",
        env=env,
    )
    missing = run_cli("research", "show", "missing", env=env, code=2)
    archived = run_cli("research", "archive", project_id, env=env)

    assert investigation["investigation"]["context"]["literature"] == "not_requested"
    assert live_degraded["investigation"]["context"]["literature"] == "unavailable"
    assert (
        "literature_unavailable"
        in live_degraded["investigation"]["context"]["degradations"]
    )
    assert missing["code"] == "invalid_research"
    assert archived["research"]["status"] == "archived"


def test_literature_tool_cli_configuration_masks_mailto(tmp_path: Path) -> None:
    env = env_for(tmp_path)

    configured = run_cli(
        "config",
        "tool",
        "set",
        "literature",
        "--mailto",
        "researcher@example.com",
        env=env,
    )

    assert configured["tools"]["literature"]["enabled"] is True
    assert configured["tools"]["literature"]["mailto"] == "***configured***"
