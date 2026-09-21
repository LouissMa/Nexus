import hashlib
from types import SimpleNamespace

import pytest

from nexus.execution_tools import build_tool_registry
from nexus.integrations.manager import build_tool_manager


def registry(root, *, report_roots=None):
    settings = {"filesystem": {"enabled": True, "roots": [str(root)],
        "report_roots": report_roots if report_roots is not None else [str(root)],
        "allowed_operations": ["list", "read", "search"]}}
    tools = build_tool_manager(settings, root / "audit")
    return build_tool_registry(tools=tools, automations=SimpleNamespace(settings={})), settings


def test_report_requires_separate_roots_and_exact_approval(tmp_path):
    tools, _ = registry(tmp_path, report_roots=[])
    assert "filesystem.create_report" not in {c["name"] for c in tools.catalog()}
    tools, _ = registry(tmp_path)
    args = {"path": str(tmp_path / "report.md"), "content": "# Result\nChecked sources."}
    assert tools.call("filesystem.create_report", args)["status"] == "approval_required"
    assert not (tmp_path / "report.md").exists()
    result = tools.call("filesystem.create_report", args, approved=True)
    assert result["status"] == "success"
    assert result["data"]["sha256"] == hashlib.sha256(args["content"].encode()).hexdigest()
    assert "content" not in result["data"]
    assert (tmp_path / "report.md").read_text() == args["content"]


@pytest.mark.parametrize("filename", ["run.py", "page.html", ".hidden.md", "CON.txt", "report.txt:stream", "report.md."])
def test_unsafe_names_are_rejected(tmp_path, filename):
    tools, _ = registry(tmp_path)
    result = tools.call("filesystem.create_report", {"path": str(tmp_path / filename), "content": "test"}, approved=True)
    assert result["status"] != "success"
    assert not (tmp_path / filename).exists()


def test_never_overwrites_existing_or_escapes_root(tmp_path):
    output = tmp_path / "out"
    output.mkdir()
    target = output / "existing.txt"
    target.write_text("original")
    tools, _ = registry(output)
    for path in [target, output / ".." / "escaped.md", tmp_path / "outside.md"]:
        assert tools.call("filesystem.create_report", {"path": str(path), "content": "replace"}, approved=True)["status"] != "success"
    assert target.read_text() == "original"
    assert not (tmp_path / "escaped.md").exists()
    assert not (tmp_path / "outside.md").exists()


def test_invalid_json_and_revoked_configuration_do_not_write(tmp_path):
    tools, settings = registry(tmp_path)
    path = tmp_path / "report.json"
    for content in ["{bad", '{"x":NaN}']:
        assert tools.call("filesystem.create_report", {"path": str(path), "content": content}, approved=True)["status"] != "success"
    settings["filesystem"]["report_roots"] = []
    assert tools.call("filesystem.create_report", {"path": str(path), "content": "{}"}, approved=True)["status"] == "denied"
    assert not path.exists()


def test_report_creation_resume_and_file_acceptance(tmp_path):
    pytest.importorskip("langgraph")
    from nexus.execution_runtime import ExecutionRuntime
    from nexus.execution_store import ExecutionStore, PersistentExecutor
    from nexus.evaluation_cases import ScriptedModel
    tools, _ = registry(tmp_path)
    path = tmp_path / "report.md"
    model = ScriptedModel([
        {"action": "tool", "tool": "filesystem.create_report", "arguments": {"path": str(path), "content": "# Research\nEvidence gap"}, "summary": "Create report"},
        {"action": "finish", "summary": "Created report", "evidence": [2]}])
    runner = PersistentExecutor(ExecutionStore(tmp_path / "runs.sqlite3"), ExecutionRuntime(tools, model))
    state = runner.start("Create report", acceptance={"checks": [{"path": str(path), "kind": "contains", "value": "Evidence gap"}]})
    assert state["status"] == "waiting_approval"
    assert not path.exists()
    state = runner.resume(state["run_id"], approval_token=state["approval_token"])
    assert state["status"] == "reported_complete"
    assert state["verification_report"]["status"] == "passed"


def test_report_config_cli_and_revocation(tmp_path, monkeypatch, capsys):
    import sys
    from nexus import cli
    from nexus.config import load_tool_settings
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("NEXUS_FILESYSTEM_ROOTS", raising=False)
    monkeypatch.setattr(sys, "argv", ["nexus", "config", "tool", "set", "filesystem", "--root", str(tmp_path), "--report-root", str(tmp_path)])
    cli.main()
    assert load_tool_settings()["filesystem"]["report_roots"] == [str(tmp_path)]
    monkeypatch.setattr(sys, "argv", ["nexus", "config", "tool", "set", "filesystem", "--clear-report-roots"])
    cli.main()
    assert load_tool_settings()["filesystem"]["report_roots"] == []


def test_direct_read_tool_api_cannot_bypass_approval(tmp_path):
    from nexus.integrations.core import ToolError
    manager = build_tool_manager({"filesystem": {"enabled": True, "roots": [str(tmp_path)],
        "report_roots": [str(tmp_path)], "allowed_operations": ["read", "list", "search"]}}, tmp_path)
    with pytest.raises(ToolError):
        manager.execute("filesystem", "create_report", path=str(tmp_path / "bad.md"), content="No approval")
    assert not (tmp_path / "bad.md").exists()


def test_existing_target_after_approval_request_is_preserved(tmp_path):
    pytest.importorskip("langgraph")
    from nexus.execution_runtime import ExecutionRuntime
    from nexus.execution_store import ExecutionStore, PersistentExecutor
    from nexus.evaluation_cases import ScriptedModel
    tools, _ = registry(tmp_path)
    target = tmp_path / "report.txt"
    action = {"action": "tool", "tool": "filesystem.create_report", "arguments": {"path": str(target), "content": "new"}, "summary": "Create"}
    runner = PersistentExecutor(ExecutionStore(tmp_path / "runs.sqlite3"), ExecutionRuntime(tools, ScriptedModel([action])))
    state = runner.start("Create")
    target.write_text("user-created")
    state = runner.resume(state["run_id"], approval_token=state["approval_token"])
    assert state["status"] == "needs_review"
    assert target.read_text() == "user-created"


def test_changed_content_invalidates_approval_binding(tmp_path):
    tools, settings = registry(tmp_path)
    first = {"path": str(tmp_path / "result.md"), "content": "A"}
    binding = tools.binding("filesystem.create_report", first)
    assert tools.binding("filesystem.create_report", {**first, "content": "B"}) != binding
    settings["filesystem"]["report_roots"] = []
    assert tools.binding("filesystem.create_report", first) != binding


def test_write_failure_is_unknown_and_keeps_file_for_manual_review(tmp_path, monkeypatch):
    import nexus.execution_artifacts as artifacts
    def fail(fd):
        raise OSError("Synthetic disk failure")
    monkeypatch.setattr(artifacts.os, "fsync", fail)
    tools, _ = registry(tmp_path)
    target = tmp_path / "partial.txt"
    result = tools.call("filesystem.create_report", {"path": str(target), "content": "Report"}, approved=True)
    assert result["status"] == "failed" and result["effect_outcome"] == "unknown"
    assert target.exists()


def test_linked_output_directory_rejected(tmp_path):
    from nexus.execution_artifacts import validate_report_roots
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("OS does not permit test symlinks")
    with pytest.raises(ValueError):
        validate_report_roots([str(link)])


def test_report_audit_does_not_contain_body(tmp_path):
    tools, _ = registry(tmp_path)
    secret = "SYNTHETIC_PRIVATE_REPORT_CONTENT"
    result = tools.call("filesystem.create_report", {"path": str(tmp_path / "report.md"), "content": secret}, approved=True)
    assert result["status"] == "success"
    for path in (tmp_path / "audit").rglob("*.jsonl"):
        assert secret not in path.read_text()


@pytest.mark.parametrize("path", ["relative/report.md", "//server/share/report.md", "C:relative.md"])
def test_non_local_absolute_paths_rejected(tmp_path, path):
    tools, _ = registry(tmp_path)
    assert tools.call("filesystem.create_report", {"path": path, "content": "Report"}, approved=True)["status"] == "failed"


@pytest.mark.parametrize("content", ["a" * 12000, "\u4e2d" * 4000], ids=["ascii", "multibyte"])
def test_full_utf8_content_budget_is_usable(tmp_path, content):
    tools, _ = registry(tmp_path)
    target = tmp_path / "report.txt"
    result = tools.call("filesystem.create_report", {"path": str(target), "content": content}, approved=True)
    assert result["status"] == "success"
    assert result["data"]["bytes"] == 12000
    assert target.read_bytes() == content.encode("utf-8")


def test_mapped_remote_drive_rejected_before_probe(tmp_path, monkeypatch):
    import os
    from pathlib import Path
    import nexus.execution_artifacts as artifacts
    if os.name != "nt":
        pytest.skip("Windows drive type check")
    monkeypatch.setattr(artifacts, "_windows_drive_type", lambda anchor: 4)
    def forbidden_probe(*args):
        raise AssertionError("Remote filesystem was probed")
    monkeypatch.setattr(Path, "is_symlink", forbidden_probe)
    with pytest.raises(ValueError, match="local"):
        artifacts.validate_report_roots([str(tmp_path)])
