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
    expected_code: int = 0,
) -> tuple[dict[str, object], subprocess.CompletedProcess[str]]:
    result = subprocess.run(
        [sys.executable, "-m", "nexus.cli", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == expected_code, result.stderr or result.stdout
    return json.loads(result.stdout), result


def isolated_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["NEXUS_HOME"] = str(tmp_path / "nexus-home")
    return env


def report_definition(tmp_path: Path, policy: str) -> str:
    root = tmp_path.resolve()
    return json.dumps(
        {
            "type": "status_report",
            "policy": policy,
            "output_path": str(root / f"{policy}.md"),
            "allowed_roots": [str(root)],
        }
    )


def test_automation_set_list_remove_and_masking(tmp_path: Path) -> None:
    env = isolated_env(tmp_path)
    definition = report_definition(tmp_path, "ask")
    saved, result = run_cli(
        "automation", "set", "weekly-report", "--definition", definition, env=env
    )
    assert saved["status"] == "ok"
    assert saved["automations"]["weekly-report"]["output_path"] == "***configured***"
    assert str(tmp_path.resolve()) not in result.stdout

    listed, result = run_cli("automation", "list", env=env)
    assert listed["automations"] == saved["automations"]
    assert str(tmp_path.resolve()) not in result.stdout

    removed, _ = run_cli("automation", "remove", "weekly-report", env=env)
    assert removed == {"status": "ok", "automations": {}}


def test_automation_policy_run_audit_and_exit_codes(tmp_path: Path) -> None:
    env = isolated_env(tmp_path)
    for name, policy in (("denied", "deny"), ("prompted", "ask"), ("allowed", "allow")):
        run_cli(
            "automation",
            "set",
            name,
            "--definition",
            report_definition(tmp_path, policy),
            env=env,
        )

    denied, _ = run_cli("automation", "run", "denied", env=env, expected_code=1)
    assert denied["code"] == "automation_denied"

    approval, _ = run_cli("automation", "run", "prompted", env=env, expected_code=1)
    assert approval["code"] == "approval_required"

    approved, _ = run_cli("automation", "run", "prompted", "--approve", env=env)
    assert approved["status"] == "ok"
    assert approved["result"]["status"] == "success"
    allowed, _ = run_cli("automation", "run", "allowed", env=env)
    assert allowed["status"] == "ok"

    audit, result = run_cli("automation", "audit", "--limit", "10", env=env)
    assert len(audit["events"]) >= 4
    assert str(tmp_path.resolve()) not in result.stdout
    assert "output_path" not in result.stdout


def test_automation_invalid_json_and_definition_are_exit_two_without_persistence(
    tmp_path: Path,
) -> None:
    env = isolated_env(tmp_path)
    invalid_json, _ = run_cli(
        "automation",
        "set",
        "broken",
        "--definition",
        "not-json",
        env=env,
        expected_code=2,
    )
    assert invalid_json["code"] == "invalid_automation_config"

    invalid_definition, _ = run_cli(
        "automation",
        "set",
        "broken",
        "--definition",
        json.dumps({"type": "browser", "url": "https://example.test"}),
        env=env,
        expected_code=2,
    )
    assert invalid_definition["code"] == "automation_configuration_invalid"
    config_path = Path(env["NEXUS_HOME"]) / "config.local.json"
    if config_path.exists():
        assert "broken" not in config_path.read_text(encoding="utf-8")
