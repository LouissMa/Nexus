from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, env: dict[str, str], check: bool = True) -> tuple[int, dict]:
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


def test_mcp_cli_configuration_policy_and_planning_binding(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["NEXUS_HOME"] = str(tmp_path / "nexus-home")

    _, added = run_cli(
        "config", "mcp", "add", "research",
        "--transport", "stdio", "--command", sys.executable,
        "--arg", "server.py", "--env", "TOKEN=top-secret",
        env=env,
    )
    assert added["status"] == "ok"
    assert added["servers"]["research"]["env"] == {"TOKEN": "***"}
    assert "top-secret" not in json.dumps(added)

    run_cli("config", "mcp", "policy", "research", "search", "allow", env=env)
    _, binding = run_cli(
        "config", "mcp", "planning-tool", "research", "search",
        "--arguments", '{"query":"Nexus"}', env=env,
    )
    assert binding["servers"]["research"]["planning_tools"][0]["tool"] == "search"

    _, shown = run_cli("config", "mcp", "show", env=env)
    assert shown["servers"]["research"]["tool_policies"] == {"search": "allow"}
    _, servers = run_cli("mcp", "servers", env=env)
    assert servers["servers"][0]["name"] == "research"

    run_cli("config", "mcp", "disable", "research", env=env)
    _, removed = run_cli("config", "mcp", "remove", "research", env=env)
    assert removed["servers"] == {}


def test_mcp_cli_rejects_invalid_json_without_connecting(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["NEXUS_HOME"] = str(tmp_path / "nexus-home")
    code, output = run_cli(
        "mcp", "call", "missing", "search", "--arguments", "not-json",
        env=env, check=False,
    )
    assert code == 2
    assert output["status"] == "error"
    assert "JSON" in output["error"]
