from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import re
import stat
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

import nexus.automation as automation_module
from nexus.automation import (
    AutomationAuditLogger,
    AutomationConfigurationError,
    AutomationExecutionError,
    AutomationManager,
    AutomationPermissionError,
    load_automation_settings,
    masked_automation_settings,
    remove_automation,
    upsert_automation,
)
from nexus.integrations.core import ToolResult
from nexus.store import JsonStore


NOW = datetime(2026, 7, 27, 9, 30, tzinfo=UTC)


def _multiprocess_config_worker(
    config_path: str,
    worker_index: int,
    start: Any,
) -> None:
    start.wait(20)
    for item_index in range(5):
        name = f"process-{worker_index}-{item_index}"
        upsert_automation(
            name,
            {
                "type": "browser",
                "url": f"https://{name}.example.test/path",
                "allowed_hosts": ["example.test"],
                "policy": "allow",
            },
            path=Path(config_path),
        )


def _multiprocess_audit_worker(
    audit_path: str,
    worker_index: int,
    start: Any,
) -> None:
    logger = AutomationAuditLogger(Path(audit_path), lambda: NOW)
    start.wait(20)
    for item_index in range(15):
        _record_audit(logger, f"audit-{worker_index}-{item_index}")


def browser_definition(**overrides: Any) -> dict[str, Any]:
    definition = {
        "type": "browser",
        "url": "https://docs.example.test/private?token=secret#fragment",
        "allowed_hosts": ["example.test"],
        "enabled": True,
        "policy": "ask",
    }
    definition.update(overrides)
    return definition


def command_definition(root: Path, **overrides: Any) -> dict[str, Any]:
    cwd = root / "work"
    cwd.mkdir(parents=True, exist_ok=True)
    definition = {
        "type": "command",
        "argv": ["python", "-c", "print('private output')"],
        "cwd": str(cwd),
        "allowed_roots": [str(root)],
        "timeout_seconds": 20,
        "max_output_bytes": 8,
        "enabled": True,
        "policy": "allow",
    }
    definition.update(overrides)
    return definition


def status_definition(root: Path, **overrides: Any) -> dict[str, Any]:
    definition = {
        "type": "status_report",
        "output_path": str(root / "reports" / "status.md"),
        "allowed_roots": [str(root)],
        "enabled": True,
        "policy": "allow",
    }
    definition.update(overrides)
    return definition


def manager(
    tmp_path: Path,
    settings: dict[str, dict[str, Any]],
    *,
    store: JsonStore | None = None,
    **kwargs: Any,
) -> AutomationManager:
    return AutomationManager(
        settings,
        tmp_path / "home",
        store or JsonStore(tmp_path / "state.json"),
        clock=lambda: NOW,
        **kwargs,
    )


def test_config_helpers_validate_before_write_preserve_other_sections_and_mask(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps({"llm": {"api_key": "keep-me"}, "extension": {"keep": True}}),
        encoding="utf-8",
    )

    settings, saved_path = upsert_automation(
        "open.docs",
        {
            "type": "browser",
            "url": "https://docs.example.test/private",
            "allowed_hosts": ["example.test"],
        },
        path=config_path,
    )

    assert saved_path == config_path
    assert settings["open.docs"]["policy"] == "ask"
    assert settings["open.docs"]["enabled"] is True
    stored = json.loads(config_path.read_text(encoding="utf-8"))
    assert stored["llm"] == {"api_key": "keep-me"}
    assert stored["extension"] == {"keep": True}

    shown = masked_automation_settings(settings)
    assert shown["open.docs"]["url"] == "***configured***"
    assert shown["open.docs"]["allowed_hosts"] == "***configured***"
    assert "docs.example.test" not in json.dumps(shown)

    before = config_path.read_bytes()
    with pytest.raises(AutomationConfigurationError):
        upsert_automation(
            "bad name",
            {"type": "browser", "url": "https://example.test"},
            path=config_path,
        )
    assert config_path.read_bytes() == before

    remaining, _ = remove_automation("open.docs", path=config_path)
    assert remaining == {}
    stored = json.loads(config_path.read_text(encoding="utf-8"))
    assert stored["extension"] == {"keep": True}


@pytest.mark.parametrize("content", ["{invalid", "[]"])
def test_config_load_failures_are_typed(tmp_path: Path, content: str) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(content, encoding="utf-8")

    with pytest.raises(AutomationConfigurationError) as failure:
        load_automation_settings(config_path)

    assert failure.value.code == "automation_configuration_invalid"


@pytest.mark.parametrize(
    "definition",
    [
        {"type": "unknown"},
        {"type": "browser", "url": "file:///tmp/private"},
        {"type": "browser", "url": "https:///missing-host"},
        {"type": "browser", "url": "https://user:pass@example.test"},
        {"type": "browser", "url": "https://example.test/path\nnext"},
        {
            "type": "browser",
            "url": "https://notexample.test",
            "allowed_hosts": ["example.test"],
        },
        {"type": "command", "argv": "echo secret"},
        {
            "type": "command",
            "argv": ["echo"],
            "cwd": ".",
            "allowed_roots": ["."],
            "timeout_seconds": 0,
        },
        {
            "type": "command",
            "argv": ["echo"],
            "cwd": ".",
            "allowed_roots": ["."],
            "env": {"TOKEN": "secret"},
        },
        {"type": "github_inspect", "limit": 101},
        {"type": "status_report", "output_path": "status.txt", "allowed_roots": ["."]},
    ],
)
def test_invalid_definitions_are_rejected(definition: dict[str, Any]) -> None:
    with pytest.raises(AutomationConfigurationError):
        AutomationManager(
            {"unsafe": definition},
            Path("home"),
            JsonStore(Path("state.json")),
        )


def test_browser_host_boundary_policy_gates_and_one_shot_approval(
    tmp_path: Path,
) -> None:
    opened: list[str] = []
    settings = {
        "denied": browser_definition(policy="deny"),
        "approval": browser_definition(policy="ask"),
        "unattended": browser_definition(policy="allow"),
        "disabled": browser_definition(enabled=False, policy="allow"),
    }
    automation = manager(
        tmp_path,
        settings,
        browser_opener=lambda url: opened.append(url) or True,
    )

    with pytest.raises(AutomationPermissionError) as denied:
        automation.run("denied", approved=True)
    assert denied.value.code == "automation_denied"

    with pytest.raises(AutomationPermissionError) as approval:
        automation.run("approval")
    assert approval.value.code == "approval_required"

    approved = automation.run("approval", approved=True)
    assert approved["host"] == "docs.example.test"
    assert "url" not in approved
    with pytest.raises(AutomationPermissionError):
        automation.run("approval")

    assert automation.run("unattended")["status"] == "success"
    with pytest.raises(AutomationPermissionError) as disabled:
        automation.run("disabled", approved=True)
    assert disabled.value.code == "automation_disabled"
    assert opened == [
        "https://docs.example.test/private?token=secret#fragment",
        "https://docs.example.test/private?token=secret#fragment",
    ]


def test_browser_exact_or_subdomain_host_matching() -> None:
    assert load_automation_settings_from(
        browser_definition(
            url="https://deep.docs.example.test/path",
            allowed_hosts=["example.test"],
        )
    )
    with pytest.raises(AutomationConfigurationError):
        load_automation_settings_from(
            browser_definition(
                url="https://example.test.evil.invalid/path",
                allowed_hosts=["example.test"],
            )
        )


def load_automation_settings_from(definition: dict[str, Any]) -> dict[str, Any]:
    return AutomationManager(
        {"browser": definition},
        Path("home"),
        JsonStore(Path("state.json")),
    ).settings


def test_command_uses_fixed_argv_no_shell_exact_cwd_and_bounded_output(
    tmp_path: Path,
) -> None:
    root = tmp_path / "allowed"
    root.mkdir()
    definition = command_definition(root)
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=b"0123456789",
            stderr=b"abcdefghij",
        )

    result = manager(
        tmp_path,
        {"fixed": definition},
        process_runner=runner,
    ).run("fixed")

    assert calls == [
        (
            ["python", "-c", "print('private output')"],
            {
                "cwd": str((root / "work").resolve()),
                "shell": False,
                "timeout": 20,
                "capture_output": True,
                "check": False,
            },
        )
    ]
    assert result["returncode"] == 0
    assert result["stdout"] == "01234567"
    assert result["stderr"] == "abcdefgh"
    assert result["stdout_truncated"] is True
    assert result["stderr_truncated"] is True


def test_command_nonzero_timeout_and_runner_errors_use_fixed_codes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "allowed"
    root.mkdir()
    definition = command_definition(root, argv=["private-command", "secret-token"])

    cases = [
        (
            lambda argv, **kwargs: subprocess.CompletedProcess(
                argv, 7, stdout=b"private output", stderr=b"secret-token"
            ),
            "command_failed",
        ),
        (
            lambda argv, **kwargs: (_ for _ in ()).throw(
                subprocess.TimeoutExpired(argv, kwargs["timeout"], output=b"private")
            ),
            "command_timeout",
        ),
        (
            lambda argv, **kwargs: (_ for _ in ()).throw(
                OSError("secret-token https://private.example/path")
            ),
            "command_execution_failed",
        ),
    ]

    for runner, code in cases:
        automation = manager(
            tmp_path,
            {"fixed": definition},
            process_runner=runner,
        )
        with pytest.raises(AutomationExecutionError) as failure:
            automation.run("fixed")
        assert failure.value.code == code
        assert "secret" not in str(failure.value)
        assert "private" not in str(failure.value)


def test_command_rejects_traversal_and_symlink_escape_where_supported(
    tmp_path: Path,
) -> None:
    root = tmp_path / "allowed"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()

    with pytest.raises(AutomationConfigurationError):
        command_definition(root, cwd=str(root / ".." / "outside"))
        AutomationManager(
            {
                "escape": command_definition(
                    root,
                    cwd=str(root / ".." / "outside"),
                )
            },
            tmp_path / "home",
            JsonStore(tmp_path / "state.json"),
        )

    link = root / "linked"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are not available for this test.")
    with pytest.raises(AutomationConfigurationError):
        AutomationManager(
            {"escape": command_definition(root, cwd=str(link))},
            tmp_path / "home",
            JsonStore(tmp_path / "state.json"),
        )


class RecordingToolManager:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.failure = failure

    def execute(self, tool: str, operation: str, **arguments: Any) -> ToolResult:
        self.calls.append((tool, operation, arguments))
        if self.failure is not None:
            raise self.failure
        return ToolResult(
            tool=tool,
            operation=operation,
            data={
                "repository": "owner/repo",
                "description": "x" * 2_000,
                "default_branch": "main",
                "stars": 4,
                "forks": 2,
                "open_issues": 3,
                "issues": [
                    {
                        "number": index,
                        "title": f"Issue {index}" + ("y" * 1_000),
                        "updated_at": "2026-07-27T00:00:00Z",
                        "html_url": f"https://secret.example/{index}?token=private",
                    }
                    for index in range(10)
                ],
                "secret_extension": "must not pass through",
            },
            executed_at=NOW.isoformat(),
        )


def test_github_inspect_uses_tool_manager_and_normalizes_bounded_metadata(
    tmp_path: Path,
) -> None:
    tools = RecordingToolManager()
    automation = manager(
        tmp_path,
        {
            "inspect": {
                "type": "github_inspect",
                "repo": "owner/repo",
                "limit": 3,
                "policy": "allow",
            }
        },
        tool_manager=tools,
    )

    result = automation.run("inspect")

    assert tools.calls == [("github", "read", {"repo": "owner/repo", "limit": 3})]
    assert result["repository"] == "owner/repo"
    assert len(result["description"]) == 1_000
    assert len(result["issues"]) == 3
    assert len(result["issues"][0]["title"]) == 500
    assert "html_url" not in result["issues"][0]
    assert "secret_extension" not in result


def test_github_failure_is_typed_without_raw_third_party_error(
    tmp_path: Path,
) -> None:
    tools = RecordingToolManager(
        failure=RuntimeError("token=private https://api.github.test/private")
    )
    automation = manager(
        tmp_path,
        {"inspect": {"type": "github_inspect", "policy": "allow"}},
        tool_manager=tools,
    )

    with pytest.raises(AutomationExecutionError) as failure:
        automation.run("inspect")

    assert failure.value.code == "github_inspect_failed"
    assert "private" not in str(failure.value)
    assert "github.test" not in str(failure.value)


def test_status_report_is_deterministic_safe_and_atomically_written(
    tmp_path: Path,
) -> None:
    root = tmp_path / "allowed"
    (root / "reports").mkdir(parents=True)
    store = JsonStore(tmp_path / "state.json")
    state = store.load()
    state["memories"] = [
        {"text": "forgotten private memory", "status": "forgotten"},
        {"text": "api_key=top-secret", "status": "active"},
    ]
    state["goals"] = [
        {"id": "goal-2", "title": "private goal title", "status": "active"},
        {"id": "goal-1", "title": "completed secret", "status": "completed"},
    ]
    state["daily_tasks"] = [
        {"id": "task-1", "status": "pending", "note": "private task text"},
        {"id": "task-2", "status": "blocked", "blocker": "secret blocker"},
        {"id": "task-3", "status": "unexpected", "note": "private"},
    ]
    state["runtime"]["job_runs"] = [
        {
            "job": "morning_briefing",
            "trigger": "manual",
            "local_date": "2026-07-27",
            "status": "success",
            "error_code": None,
            "body": "private generated briefing",
            "webhook_url": "https://hooks.example/private",
        },
        {
            "job": "secret-job-name",
            "trigger": "private-trigger",
            "local_date": "private-date",
            "status": "private-status",
            "error_code": "token=secret",
        },
    ]
    store.save(state)
    automation = manager(
        tmp_path,
        {"report": status_definition(root)},
        store=store,
    )

    first = automation.run("report")
    first_text = (root / "reports" / "status.md").read_text(encoding="utf-8")
    second = automation.run("report")
    second_text = (root / "reports" / "status.md").read_text(encoding="utf-8")

    assert first == second
    assert first_text == second_text
    assert first["bytes_written"] == len(first_text.encode("utf-8"))
    assert "# Nexus Status Report" in first_text
    assert "- Memories: 2" in first_text
    assert "- Active goals: 1" in first_text
    assert "goal-2" not in first_text
    assert re.search(r"goal-[0-9a-f]{12}", first_text)
    assert "- pending: 1" in first_text
    assert "- blocked: 1" in first_text
    assert "morning_briefing | manual | 2026-07-27 | success | none" in first_text
    encoded = json.dumps(first) + first_text
    for private in (
        "forgotten private memory",
        "top-secret",
        "private goal title",
        "completed secret",
        "private task text",
        "secret blocker",
        "private generated briefing",
        "hooks.example",
        "secret-job-name",
        "private-trigger",
        "token=secret",
    ):
        assert private not in encoded
    assert not list((root / "reports").glob("*.tmp"))


def test_status_report_rejects_traversal_and_symlink_escape_where_supported(
    tmp_path: Path,
) -> None:
    root = tmp_path / "allowed"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    with pytest.raises(AutomationConfigurationError):
        AutomationManager(
            {
                "report": status_definition(
                    root,
                    output_path=str(root / ".." / "outside" / "status.md"),
                )
            },
            tmp_path / "home",
            JsonStore(tmp_path / "state.json"),
        )

    link = root / "linked"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are not available for this test.")
    with pytest.raises(AutomationConfigurationError):
        AutomationManager(
            {
                "report": status_definition(
                    root,
                    output_path=str(link / "status.md"),
                )
            },
            tmp_path / "home",
            JsonStore(tmp_path / "state.json"),
        )


def test_audit_is_bounded_redacted_and_skips_corrupt_lines(
    tmp_path: Path,
) -> None:
    secret_url = "https://docs.example.test/private?token=secret#fragment"
    secret_argv = ["private-command", "secret-token"]
    root = tmp_path / "allowed"
    root.mkdir()
    command = command_definition(root, argv=secret_argv)

    def failing_runner(
        argv: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            argv,
            9,
            stdout=b"private stdout",
            stderr=b"secret-token",
        )

    automation = manager(
        tmp_path,
        {
            "open": browser_definition(url=secret_url, policy="deny"),
            "command": command,
        },
        process_runner=failing_runner,
    )
    with pytest.raises(AutomationPermissionError):
        automation.run("open", approved=True)
    with pytest.raises(AutomationExecutionError):
        automation.run("command")

    audit_path = tmp_path / "home" / "automation_audit.jsonl"
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write("{corrupt\n")
        handle.write(json.dumps({"unexpected": "record"}) + "\n")
    events = automation.audit_events(limit=10)

    assert len(events) == 2
    assert events[0] == {
        "at": "2026-07-27T09:30:00+00:00",
        "action": "sha256:" + hashlib.sha256(b"open").hexdigest()[:12],
        "type": "browser",
        "policy": "deny",
        "decision": "deny",
        "status": "denied",
        "duration_ms": 0,
        "error_code": "automation_denied",
        "summary": "Automation blocked by policy.",
    }
    assert events[1]["error_code"] == "command_failed"
    assert events[1]["summary"] == "Automation execution failed."
    encoded = audit_path.read_text(encoding="utf-8")
    for secret in (
        secret_url,
        "docs.example.test",
        "private-command",
        "secret-token",
        "private stdout",
        str(root),
        str(root / "work"),
    ):
        assert secret not in encoded


@pytest.mark.parametrize("policy", ["deny", "ask", "allow"])
def test_browser_requires_nonempty_allowed_hosts_for_every_policy(policy: str) -> None:
    with pytest.raises(AutomationConfigurationError, match="allowed_hosts"):
        AutomationManager(
            {
                "browser": {
                    "type": "browser",
                    "url": "https://example.test/path",
                    "allowed_hosts": [],
                    "policy": policy,
                }
            },
            Path("home"),
            JsonStore(Path("state.json")),
        )


def test_manager_uses_deep_immutable_canonical_snapshot_under_mutation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "allowed"
    root.mkdir()
    original_url = "https://docs.example.test/original"
    source = {
        "open": browser_definition(url=original_url, policy="allow"),
        "command": command_definition(
            root,
            argv=["fixed-program", "fixed-argument"],
            cwd=str(root / "work" / ".." / "work"),
        ),
    }
    opened: list[str] = []
    command_calls: list[list[str]] = []

    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        command_calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    automation = manager(
        tmp_path,
        source,
        browser_opener=lambda url: opened.append(url) or True,
        process_runner=runner,
    )
    source["open"]["policy"] = "deny"
    source["open"]["url"] = "https://evil.invalid/stolen"
    source["command"]["argv"].append("attacker-suffix")

    assert isinstance(automation.settings, MappingProxyType)
    assert isinstance(automation.settings["open"], MappingProxyType)
    assert automation.settings["command"]["argv"] == (
        "fixed-program",
        "fixed-argument",
    )
    assert automation.settings["command"]["cwd"] == str((root / "work").resolve())
    assert automation.settings["command"]["allowed_roots"] == (str(root.resolve()),)
    with pytest.raises(TypeError):
        automation.settings["open"]["policy"] = "deny"  # type: ignore[index]
    with pytest.raises(AttributeError):
        automation.settings = MappingProxyType({})  # type: ignore[misc]

    def mutate_source() -> None:
        for _ in range(200):
            source["open"]["url"] = "https://evil.invalid/race"
            source["open"]["policy"] = "deny"

    mutator = threading.Thread(target=mutate_source)
    mutator.start()
    for _ in range(20):
        automation.run("open")
    mutator.join()
    automation.run("command")

    assert opened == [original_url] * 20
    assert command_calls == [["fixed-program", "fixed-argument"]]


def test_config_rejects_invalid_existing_sibling_without_changing_bytes(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "extension": {"keep": True},
                "automations": {"broken": {"type": "github_inspect", "limit": 0}},
            }
        ),
        encoding="utf-8",
    )
    before = config_path.read_bytes()

    with pytest.raises(AutomationConfigurationError):
        upsert_automation(
            "valid",
            browser_definition(
                url="https://example.test", allowed_hosts=["example.test"]
            ),
            path=config_path,
        )

    assert config_path.read_bytes() == before


def test_config_mutations_are_atomic_canonical_and_do_not_lose_concurrent_updates(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(json.dumps({"extension": {"keep": True}}), encoding="utf-8")
    root = tmp_path / "allowed"
    work = root / "work"
    work.mkdir(parents=True)

    _, _ = upsert_automation(
        "canonical",
        command_definition(
            root,
            cwd=str(work / ".." / "work"),
            allowed_roots=[str(root / ".")],
        ),
        path=config_path,
    )
    canonical = json.loads(config_path.read_text(encoding="utf-8"))["automations"][
        "canonical"
    ]
    assert canonical["cwd"] == str(work.resolve())
    assert canonical["allowed_roots"] == [str(root.resolve())]

    names = [f"browser-{index}" for index in range(32)]
    gate = threading.Barrier(len(names))

    def add(name: str) -> None:
        gate.wait()
        upsert_automation(
            name,
            browser_definition(
                url=f"https://{name}.example.test/path",
                allowed_hosts=["example.test"],
            ),
            path=config_path,
        )

    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        list(pool.map(add, names))

    remove_names = names[::2]
    gate = threading.Barrier(len(remove_names))

    def remove(name: str) -> None:
        gate.wait()
        remove_automation(name, path=config_path)

    with ThreadPoolExecutor(max_workers=len(remove_names)) as pool:
        list(pool.map(remove, remove_names))

    stored = json.loads(config_path.read_text(encoding="utf-8"))
    assert stored["extension"] == {"keep": True}
    assert set(stored["automations"]) == {"canonical", *names[1::2]}
    assert not list(tmp_path.glob(".*.tmp"))


def test_command_rejects_detectable_directory_replacement_before_runner(
    tmp_path: Path,
) -> None:
    root = tmp_path / "allowed"
    root.mkdir()
    definition = command_definition(root)
    called = False

    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        nonlocal called
        called = True
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    automation = manager(
        tmp_path,
        {"command": definition},
        process_runner=runner,
    )
    cwd = root / "work"
    cwd.rename(root / "work-original")
    cwd.mkdir()

    with pytest.raises(AutomationExecutionError) as failure:
        automation.run("command")

    assert failure.value.code == "path_identity_changed"
    assert called is False


def test_report_rejects_detectable_parent_replacement_before_write(
    tmp_path: Path,
) -> None:
    root = tmp_path / "allowed"
    reports = root / "reports"
    reports.mkdir(parents=True)
    automation = manager(
        tmp_path,
        {"report": status_definition(root)},
    )
    reports.rename(root / "reports-original")
    reports.mkdir()

    with pytest.raises(AutomationExecutionError) as failure:
        automation.run("report")

    assert failure.value.code == "path_identity_changed"
    assert not (reports / "status.md").exists()


def test_default_runner_hard_bounds_real_subprocess_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "allowed"
    root.mkdir()
    payload_bytes = 2_000_000
    definition = command_definition(
        root,
        argv=[
            sys.executable,
            "-c",
            (
                "import os;"
                f"os.write(1, b'x' * {payload_bytes});"
                f"os.write(2, b'y' * {payload_bytes})"
            ),
        ],
        max_output_bytes=4_096,
        timeout_seconds=20,
    )

    def forbidden_run(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("default command execution must not use subprocess.run")

    monkeypatch.setattr(subprocess, "run", forbidden_run)
    result = manager(tmp_path, {"command": definition}).run("command")

    assert result["stdout"] == "x" * 4_096
    assert result["stderr"] == "y" * 4_096
    assert result["stdout_truncated"] is True
    assert result["stderr_truncated"] is True


def test_default_runner_timeout_cleans_up_spawned_child_process(
    tmp_path: Path,
) -> None:
    root = tmp_path / "allowed"
    root.mkdir()
    marker = tmp_path / "child-survived.txt"
    child = (
        "import time;"
        "from pathlib import Path;"
        "time.sleep(2);"
        f"Path({str(marker)!r}).write_text('alive', encoding='utf-8')"
    )
    parent = (
        "import subprocess,time;"
        f"subprocess.Popen([{sys.executable!r}, '-c', {child!r}]);"
        "time.sleep(30)"
    )
    definition = command_definition(
        root,
        argv=[sys.executable, "-c", parent],
        timeout_seconds=1,
        max_output_bytes=1_024,
    )

    with pytest.raises(AutomationExecutionError) as failure:
        manager(tmp_path, {"command": definition}).run("command")

    assert failure.value.code == "command_timeout"
    time.sleep(2.5)
    assert not marker.exists()


def _record_audit(logger: AutomationAuditLogger, action: str) -> None:
    logger.record(
        action=action,
        automation_type="browser",
        policy="allow",
        decision="allow",
        status="success",
        duration_ms=1,
        error_code=None,
        summary="Automation completed.",
    )


def test_audit_concurrent_append_rotation_tail_read_and_semantic_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "automation_audit.jsonl"
    logger = AutomationAuditLogger(path, lambda: NOW)
    monkeypatch.setattr(logger, "MAX_EVENTS", 12, raising=False)
    monkeypatch.setattr(logger, "MAX_BYTES", 4_096, raising=False)

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(
            pool.map(lambda index: _record_audit(logger, f"action-{index}"), range(80))
        )

    lines = path.read_bytes().splitlines()
    assert 1 <= len(lines) <= 12
    assert all(json.loads(line) for line in lines)

    malicious = {
        "at": "2026-07-27T09:30:00+00:00",
        "action": "sk-private-api-key",
        "type": "browser",
        "policy": "allow",
        "decision": "allow",
        "status": "success",
        "duration_ms": 1,
        "error_code": None,
        "summary": "https://private.example/?token=secret",
    }
    with path.open("ab") as handle:
        handle.write(json.dumps(malicious).encode("utf-8") + b"\n")

    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("recent must use a bounded tail read")
        ),
    )
    events = logger.recent(limit=5)

    assert len(events) <= 5
    assert all(event["summary"] == "Automation completed." for event in events)
    assert "private-api-key" not in json.dumps(events)


@pytest.mark.parametrize("outcome", ["denied", "execution", "success"])
def test_audit_write_failure_never_replaces_primary_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    root = tmp_path / "allowed"
    root.mkdir()
    settings: dict[str, dict[str, Any]]
    kwargs: dict[str, Any] = {}
    if outcome == "denied":
        settings = {"action": browser_definition(policy="deny")}
    elif outcome == "execution":
        settings = {"action": command_definition(root)}
        kwargs["process_runner"] = lambda argv, **options: subprocess.CompletedProcess(
            argv, 3, stdout=b"", stderr=b"private"
        )
    else:
        settings = {"action": browser_definition(policy="allow")}
        kwargs["browser_opener"] = lambda url: True
    automation = manager(tmp_path, settings, **kwargs)

    def fail_audit(**fields: Any) -> None:
        raise OSError("private audit path failure")

    monkeypatch.setattr(automation._audit_logger, "record", fail_audit)

    if outcome == "denied":
        with pytest.raises(AutomationPermissionError) as failure:
            automation.run("action")
        assert failure.value.code == "automation_denied"
        assert failure.value.audit_warning == "audit_write_failed"
    elif outcome == "execution":
        with pytest.raises(AutomationExecutionError) as failure:
            automation.run("action")
        assert failure.value.code == "command_failed"
        assert failure.value.audit_warning == "audit_write_failed"
    else:
        result = automation.run("action")
        assert result["status"] == "success"
        assert result["audit_warning"] == "audit_write_failed"

    assert automation.audit_health == {
        "status": "degraded",
        "warning": "audit_write_failed",
    }


def test_audit_hashes_api_key_shaped_action_names(tmp_path: Path) -> None:
    action = "sk-abcdefgh"
    automation = manager(
        tmp_path,
        {action: browser_definition(policy="deny")},
    )

    with pytest.raises(AutomationPermissionError):
        automation.run(action)

    event = automation.audit_events()[0]
    assert event["action"].startswith("sha256:")
    assert action not in json.dumps(event)


def test_status_report_hashes_goal_and_scheduler_identifiers(
    tmp_path: Path,
) -> None:
    root = tmp_path / "allowed"
    (root / "reports").mkdir(parents=True)
    store = JsonStore(tmp_path / "state.json")
    state = store.load()
    goal_id = "sk-goal-secret-identifier"
    run_id = "sk-run-secret-identifier"
    state["goals"] = [{"id": goal_id, "status": "active"}]
    state["runtime"]["job_runs"] = [
        {
            "id": run_id,
            "job": "morning_briefing",
            "trigger": "manual",
            "local_date": "2026-07-27",
            "status": "success",
            "error_code": None,
        }
    ]
    store.save(state)

    manager(
        tmp_path,
        {"report": status_definition(root)},
        store=store,
    ).run("report")
    report = (root / "reports" / "status.md").read_text(encoding="utf-8")

    assert goal_id not in report
    assert run_id not in report
    assert re.search(r"goal-[0-9a-f]{12}", report)
    assert re.search(r"run-[0-9a-f]{12}", report)


@pytest.mark.parametrize(
    "action",
    [
        "ordinary",
        "ghp-token-shaped",
        "AKIA-TOKEN-SHAPED",
        "arbitrary.token_like-valid",
    ],
)
def test_audit_hashes_every_action_name(tmp_path: Path, action: str) -> None:
    automation = manager(
        tmp_path,
        {action: browser_definition(policy="deny")},
    )

    with pytest.raises(AutomationPermissionError):
        automation.run(action)

    event = automation.audit_events()[0]
    expected = hashlib.sha256(action.encode("utf-8")).hexdigest()[:12]
    assert event["action"] == f"sha256:{expected}"
    assert action not in json.dumps(event)


def test_config_updates_are_interprocess_safe_across_alias_paths(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.local.json"
    alias_dir = tmp_path / "alias"
    alias_dir.mkdir()
    alias_path = alias_dir / ".." / config_path.name
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    processes = [
        context.Process(
            target=_multiprocess_config_worker,
            args=(
                str(config_path if worker_index % 2 == 0 else alias_path),
                worker_index,
                start,
            ),
        )
        for worker_index in range(6)
    ]

    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(30)
        assert process.exitcode == 0

    settings = load_automation_settings(config_path)
    assert set(settings) == {
        f"process-{worker_index}-{item_index}"
        for worker_index in range(6)
        for item_index in range(5)
    }


def test_audit_appends_are_interprocess_safe_across_alias_paths(
    tmp_path: Path,
) -> None:
    audit_path = tmp_path / "automation_audit.jsonl"
    alias_dir = tmp_path / "alias"
    alias_dir.mkdir()
    alias_path = alias_dir / ".." / audit_path.name
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    processes = [
        context.Process(
            target=_multiprocess_audit_worker,
            args=(
                str(audit_path if worker_index % 2 == 0 else alias_path),
                worker_index,
                start,
            ),
        )
        for worker_index in range(6)
    ]

    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(30)
        assert process.exitcode == 0

    events = AutomationAuditLogger(audit_path, lambda: NOW).recent(limit=100)
    expected = {
        "sha256:"
        + hashlib.sha256(
            f"audit-{worker_index}-{item_index}".encode("utf-8")
        ).hexdigest()[:12]
        for worker_index in range(6)
        for item_index in range(15)
    }
    assert len(events) == 90
    assert {event["action"] for event in events} == expected


def test_audit_tail_read_caps_bytes_and_rejects_huge_unterminated_tail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "automation_audit.jsonl"
    logger = AutomationAuditLogger(path, lambda: NOW)
    _record_audit(logger, "prior-valid")
    with path.open("ab") as handle:
        handle.write(b"x" * 1_000_000)

    monkeypatch.setattr(logger, "TAIL_READ_BYTES", 1_024, raising=False)
    monkeypatch.setattr(logger, "MAX_SCAN_BYTES", 4_096, raising=False)
    monkeypatch.setattr(logger, "MAX_LINE_BYTES", 2_048, raising=False)
    original_open = Path.open
    bytes_read = 0

    class CountingReader:
        def __init__(self, handle: Any) -> None:
            self.handle = handle

        def __enter__(self) -> CountingReader:
            return self

        def __exit__(self, *args: Any) -> None:
            self.handle.close()

        def read(self, size: int = -1) -> bytes:
            nonlocal bytes_read
            data = self.handle.read(size)
            bytes_read += len(data)
            assert bytes_read <= logger.MAX_SCAN_BYTES
            return data

        def __getattr__(self, name: str) -> Any:
            return getattr(self.handle, name)

    def tracked_open(
        candidate: Path,
        mode: str = "r",
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        handle = original_open(candidate, mode, *args, **kwargs)
        if candidate == path and mode == "rb":
            return CountingReader(handle)
        return handle

    monkeypatch.setattr(Path, "open", tracked_open)

    assert logger.recent(limit=10) == []
    assert bytes_read <= logger.MAX_SCAN_BYTES


def test_audit_append_separates_corrupt_tail_and_rotation_retains_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "automation_audit.jsonl"
    logger = AutomationAuditLogger(path, lambda: NOW)
    monkeypatch.setattr(logger, "MAX_BYTES", 10_000, raising=False)
    monkeypatch.setattr(logger, "MAX_SCAN_BYTES", 8_192, raising=False)
    monkeypatch.setattr(logger, "MAX_LINE_BYTES", 512, raising=False)
    path.write_bytes(b"x" * 4_096)
    original_open = Path.open
    append_writes: list[bytes] = []

    class RecordingWriter:
        def __init__(self, handle: Any) -> None:
            self.handle = handle

        def __enter__(self) -> RecordingWriter:
            return self

        def __exit__(self, *args: Any) -> None:
            self.handle.close()

        def write(self, payload: bytes) -> int:
            append_writes.append(payload)
            return self.handle.write(payload)

        def __getattr__(self, name: str) -> Any:
            return getattr(self.handle, name)

    def tracked_open(
        candidate: Path,
        mode: str = "r",
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        handle = original_open(candidate, mode, *args, **kwargs)
        if candidate == path and mode == "ab":
            return RecordingWriter(handle)
        return handle

    monkeypatch.setattr(Path, "open", tracked_open)

    _record_audit(logger, "survives-rotation")
    surviving_action = "sha256:" + hashlib.sha256(b"survives-rotation").hexdigest()[:12]
    assert [event["action"] for event in logger.recent()] == [surviving_action]
    assert len(append_writes) == 1
    assert append_writes[0].startswith(b"\n{")
    assert not append_writes[0].startswith(b"\n\n")

    monkeypatch.setattr(logger, "MAX_BYTES", 1_024, raising=False)
    _record_audit(logger, "rotation-trigger")

    assert surviving_action in {event["action"] for event in logger.recent()}
    assert path.stat().st_size <= logger.MAX_BYTES


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode semantics")
def test_config_replacement_preserves_private_posix_mode(tmp_path: Path) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text('{"unrelated": true}\n', encoding="utf-8")
    config_path.chmod(0o600)

    upsert_automation(
        "open",
        browser_definition(policy="allow"),
        path=config_path,
    )

    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode semantics")
def test_new_config_is_private_on_posix(tmp_path: Path) -> None:
    config_path = tmp_path / "config.local.json"

    upsert_automation(
        "open",
        browser_definition(policy="allow"),
        path=config_path,
    )

    assert stat.S_IMODE(config_path.stat().st_mode) & 0o077 == 0


def test_existing_windows_config_uses_acl_preserving_replacement(
    tmp_path: Path,
) -> None:
    source = tmp_path / "temporary"
    destination = tmp_path / "config.local.json"
    source.write_text("new", encoding="utf-8")
    destination.write_text("old", encoding="utf-8")
    calls: list[tuple[Path, Path]] = []

    def replace_file(candidate: Path, target: Path) -> None:
        calls.append((candidate, target))
        os.replace(candidate, target)

    automation_module._replace_preserving_metadata(
        source,
        destination,
        platform_name="nt",
        windows_replacer=replace_file,
    )

    assert calls == [(source, destination)]
    assert destination.read_text(encoding="utf-8") == "new"


def test_config_replace_failure_is_typed_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.local.json"
    original = b'{"unrelated": true}\n'
    config_path.write_bytes(original)

    def fail_replace(*args: Any, **kwargs: Any) -> None:
        raise AutomationConfigurationError("Unable to save automation configuration.")

    monkeypatch.setattr(
        automation_module,
        "_replace_preserving_metadata",
        fail_replace,
    )

    with pytest.raises(AutomationConfigurationError):
        upsert_automation(
            "open",
            browser_definition(policy="allow"),
            path=config_path,
        )

    assert config_path.read_bytes() == original
    assert list(tmp_path.glob(f".{config_path.name}.*.tmp")) == []
