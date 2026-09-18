import json
from unittest.mock import Mock

import pytest

from nexus.execution_store import ExecutionStore, PersistentExecutor
from nexus.execution_runtime import ExecutionRuntime
from nexus.execution_tools import build_tool_registry
from test_execution_store import Model, CALL, registry


def file_tools(tmp_path):
    from nexus.integrations.manager import build_tool_manager
    settings = {"filesystem": {"enabled": True, "roots": [str(tmp_path)], "allowed_operations": ["read"]}}
    manager = build_tool_manager(settings, tmp_path / "audit")
    return build_tool_registry(tools=manager, automations=Mock(settings={})), settings


def acceptance(path, kind="nonempty", **extra):
    return {"checks": [{"path": str(path), "kind": kind, **extra}]}


def test_actual_files_and_private_content_not_in_report(tmp_path):
    from nexus.execution_verification import FileVerifier
    path = tmp_path / "report.txt"
    path.write_text("PRIVATE_FILE_CONTENT: completed", encoding="utf-8")
    tools, _ = file_tools(tmp_path)
    verifier = FileVerifier(tools)
    report = verifier.verify(acceptance(path, "contains", value="completed"))
    assert report["status"] == "passed"
    assert report["checked_at"]
    assert "PRIVATE_FILE_CONTENT" not in json.dumps(report)
    path.write_text("unfinished", encoding="utf-8")
    assert verifier.verify(acceptance(path, "contains", value="completed"))["status"] == "failed"


@pytest.mark.parametrize("kind,content,extra,status", [
    ("exists", "", {}, "passed"),
    ("nonempty", "", {}, "failed"),
    ("nonempty", "hello", {}, "passed"),
    ("contains", "abc", {"value": "z"}, "failed"),
    ("json_fields", '{"name":"ok","count":2}', {"fields": {"name": "string", "count": "integer"}}, "passed"),
    ("json_fields", '{"count":true}', {"fields": {"count": "integer"}}, "failed"),
    ("json_fields", '{"count":1.5}', {"fields": {"count": "integer"}}, "failed"),
    ("json_fields", '{"count":null}', {"fields": {"count": "null"}}, "passed"),
    ("json_fields", '[]', {"fields": {"name": "string"}}, "failed"),
    ("json_fields", 'not json', {"fields": {"name": "string"}}, "failed"),
])
def test_check_types(tmp_path, kind, content, extra, status):
    from nexus.execution_verification import FileVerifier
    path = tmp_path / "report.txt"
    path.write_text(content, encoding="utf-8")
    tools, _ = file_tools(tmp_path)
    assert FileVerifier(tools).verify(acceptance(path, kind, **extra))["status"] == status


def test_permissions_missing_and_truncation_are_not_success(tmp_path):
    from nexus.execution_verification import FileVerifier
    tools, settings = file_tools(tmp_path)
    verifier = FileVerifier(tools)
    assert verifier.verify(acceptance(tmp_path / "missing.txt"))["status"] == "unverifiable"
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside")
    assert verifier.verify(acceptance(outside))["status"] == "unverifiable"
    path = tmp_path / "large.txt"
    path.write_text("x" * 16001)
    assert verifier.verify(acceptance(path))["status"] == "unverifiable"
    path.write_text("safe")
    settings["filesystem"]["allowed_operations"] = []
    assert verifier.verify(acceptance(path))["status"] == "unverifiable"


def test_partial_and_cooperative_budget(tmp_path):
    from nexus.execution_verification import FileVerifier
    path = tmp_path / "report.txt"
    path.write_text("hello")
    tools, _ = file_tools(tmp_path)
    checks = {"checks": [acceptance(path)["checks"][0], acceptance(path, "contains", value="absent")["checks"][0]]}
    assert FileVerifier(tools).verify(checks)["status"] == "partial"
    ticks = iter([0, 6, 6, 6])
    blocked = Mock()
    assert FileVerifier(blocked, clock=lambda: next(ticks)).verify(checks)["status"] == "unverifiable"
    blocked.call.assert_not_called()


@pytest.mark.parametrize("value", [None, {}, {"checks": []}, {"checks": [None]},
    {"checks": [{"path": "relative.txt", "kind": "exists"}]},
    {"checks": [{"path": "", "kind": "exists"}]},
    {"checks": [{"path": "D:/r.txt", "kind": "shell", "command": "test"}]},
    {"checks": [{"path": "D:/r.txt", "kind": "contains", "value": ""}]},
    {"checks": [{"path": "D:/r.txt", "kind": "json_fields", "fields": {"a": "eval"}}]},
])
def test_invalid_contracts(value):
    from nexus.execution_verification import validate_acceptance
    with pytest.raises(ValueError):
        validate_acceptance(value)


def test_contract_copied_before_execution_and_recheck_after_restart(tmp_path):
    pytest.importorskip("langgraph")
    from nexus.execution_verification import FileVerifier
    path = tmp_path / "report.txt"
    path.write_text("required")
    contract = acceptance(path, "contains", value="required")
    tools, _ = file_tools(tmp_path)
    def act(*args):
        contract["checks"][0]["value"] = "weaker"
        return {}
    model = Model(CALL, {"action": "finish", "summary": "Done", "evidence": [1]})
    store = ExecutionStore(tmp_path / "runs.sqlite3")
    runner = PersistentExecutor(store, ExecutionRuntime(registry(act, "allow"), model), verifier=FileVerifier(tools))
    state = runner.start("Test", acceptance=contract)
    assert state["status"] == "reported_complete"
    assert state["verification_report"]["status"] == "passed"
    assert model.prompts[0]["acceptance"]["checks"][0]["value"] == "required"
    assert state["acceptance"]["checks"][0]["value"] == "required"
    path.write_text("changed")
    restored = PersistentExecutor(ExecutionStore(store.path), None, verifier=FileVerifier(tools))
    result = restored.verify(state["run_id"])
    assert result["verification_report"]["status"] == "failed"
    assert result["verification_history"][0]["status"] == "passed"
    assert len(model.prompts) == 2


def test_no_posthoc_contract_or_cancelled_task_verification(tmp_path):
    from nexus.execution_verification import FileVerifier
    store = ExecutionStore(tmp_path / "runs.sqlite3")
    verifier = Mock(spec=FileVerifier)
    executor = PersistentExecutor(store, None, verifier=verifier)
    for state in [{"status": "reported_complete"}, {"status": "cancelled", "acceptance": acceptance(tmp_path / "r.txt")}]:
        run = store.create({"goal": "test", **state})
        with pytest.raises(ValueError):
            executor.verify(run["run_id"])
    verifier.verify.assert_not_called()


def test_cli_verify_without_llm_or_embedding(tmp_path, monkeypatch, capsys):
    import sys
    from nexus import cli
    from nexus.config import update_tool_settings
    home = tmp_path / "home"
    monkeypatch.setenv("NEXUS_HOME", str(home))
    monkeypatch.delenv("NEXUS_FILESYSTEM_ROOTS", raising=False)
    update_tool_settings("filesystem", {"roots": [str(tmp_path)]})
    path = tmp_path / "r.txt"
    path.write_text("ok")
    store = ExecutionStore(home / "executor.sqlite3")
    state = store.create({"goal": "test", "status": "reported_complete", "acceptance": acceptance(path)})
    monkeypatch.setattr(cli.LLMConfig, "from_env", Mock(side_effect=AssertionError("No LLM")))
    monkeypatch.setattr(cli, "load_embedding_settings", Mock(side_effect=AssertionError("No embeddings")))
    monkeypatch.setattr(sys, "argv", ["nexus", "executor", "verify", state["run_id"]])
    cli.main()
    assert json.loads(capsys.readouterr().out)["verification_report"]["status"] == "passed"
    path.write_text("")
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    assert json.loads(capsys.readouterr().out)["verification_report"]["status"] == "failed"


def test_cli_invalid_acceptance_before_model_init(tmp_path, monkeypatch, capsys):
    import sys
    from nexus import cli
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    monkeypatch.setattr(cli.LLMConfig, "from_env", Mock(side_effect=AssertionError("No LLM")))
    monkeypatch.setattr(sys, "argv", ["nexus", "executor", "run", "test", "--acceptance", '{"checks":[]}'])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"


@pytest.mark.parametrize("verdict", ["passed", "partial", "failed", "unverifiable"])
def test_shared_status_reports_checks_without_speaking_private_details(tmp_path, verdict):
    from nexus.task_conversation import TaskConversation
    from nexus.voice import render_conversation_speech
    store = ExecutionStore(tmp_path / "runs.sqlite3")
    state = store.create({"goal": "test", "status": "reported_complete", "verification": "file_conditions_" + verdict,
        "verification_report": {"status": verdict, "counts": {"passed": 1, "failed": 0, "unverifiable": 0},
            "checked_at": "2026-09-18T00:00:00+00:00", "checks": [{"path": "PRIVATE_PATH"}]}})
    response = TaskConversation(store, Mock(side_effect=AssertionError("No LLM")), run_id=state["run_id"]).handle("status")
    assert response["result"]["task"]["verification"]["status"] == verdict
    speech = render_conversation_speech(response)
    assert "PRIVATE_PATH" not in speech
    assert "declared file" in speech.lower()
    assert "not been independently verified" not in speech


def test_manifest_limits_and_isolation(tmp_path):
    from nexus.execution_verification import validate_acceptance
    item = acceptance(tmp_path / "r.txt")["checks"][0]
    invalid = [{"checks": [item] * 21}, {"checks": [item], "extra": True},
               acceptance(tmp_path / "r.txt", "contains", value="x" * 1001),
               acceptance(tmp_path / "r.txt", "json_fields", fields={str(i): "string" for i in range(31)}),
               {"checks": [acceptance(tmp_path / "r.txt", "contains", value="x" * 1000)["checks"][0]] * 20}]
    for contract in invalid:
        with pytest.raises(ValueError):
            validate_acceptance(contract)
    original = {"checks": [item]}
    copied = validate_acceptance(original)
    original["checks"][0]["kind"] = "exists"
    assert copied["checks"][0]["kind"] == "nonempty"


@pytest.mark.parametrize("body", ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":1e400}'])
def test_ambiguous_or_nonfinite_json_not_verified(tmp_path, body):
    from nexus.execution_verification import FileVerifier
    path = tmp_path / "r.json"
    path.write_text(body)
    tools, _ = file_tools(tmp_path)
    assert FileVerifier(tools).verify(acceptance(path, "json_fields", fields={"a": "number"}))["status"] == "failed"


def test_nested_nonfinite_json_is_invalid(tmp_path):
    from nexus.execution_verification import FileVerifier
    path = tmp_path / "r.json"
    path.write_text('{"a":{"nested":1e400}}')
    tools, _ = file_tools(tmp_path)
    assert FileVerifier(tools).verify(acceptance(path, "json_fields", fields={"a": "object"}))["status"] == "failed"


def test_interrupted_verification_recovers_without_execution_and_bounds_history(tmp_path):
    from nexus.execution_verification import FileVerifier
    path = tmp_path / "r.txt"
    path.write_text("ok")
    tools, _ = file_tools(tmp_path)
    store = ExecutionStore(tmp_path / "runs.sqlite3")
    state = store.create({"goal": "test", "status": "reported_complete", "acceptance": acceptance(path)})
    broken = Mock()
    broken.verify.side_effect = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        PersistentExecutor(store, None, verifier=broken).verify(state["run_id"])
    assert store.get(state["run_id"])["verification"] == "pending_file_checks"
    runner = PersistentExecutor(ExecutionStore(store.path), None, verifier=FileVerifier(tools))
    for _ in range(12):
        result = runner.verify(state["run_id"])
    assert result["verification_report"]["status"] == "passed"
    assert len(result["verification_history"]) == 10


@pytest.mark.parametrize("expected,code", [("present", None), ("absent", 1)])
def test_cli_run_acceptance_and_exit_status(tmp_path, monkeypatch, capsys, expected, code):
    pytest.importorskip("langgraph")
    import sys
    from nexus import cli
    from nexus.config import update_tool_settings
    home = tmp_path / "home"
    monkeypatch.setenv("NEXUS_HOME", str(home))
    monkeypatch.delenv("NEXUS_FILESYSTEM_ROOTS", raising=False)
    update_tool_settings("filesystem", {"roots": [str(tmp_path)]})
    path = tmp_path / "r.txt"
    path.write_text("present")
    model = Model({"action": "tool", "tool": "filesystem.read", "arguments": {"path": str(path)}, "summary": "Read"},
                  {"action": "finish", "summary": "Done", "evidence": [1]})
    monkeypatch.setattr(cli.LLMConfig, "from_env", lambda **kwargs: Mock(is_configured=True))
    monkeypatch.setattr(cli, "OpenAICompatibleLLM", lambda config: model)
    monkeypatch.setattr(sys, "argv", ["nexus", "executor", "run", "Check report", "--acceptance",
                                     json.dumps(acceptance(path, "contains", value=expected))])
    if code is None:
        cli.main()
    else:
        with pytest.raises(SystemExit) as error:
            cli.main()
        assert error.value.code == code
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "reported_complete"
    assert result["verification_report"]["status"] == ("passed" if code is None else "failed")


def test_symlink_escape_does_not_pass(tmp_path):
    from nexus.execution_verification import FileVerifier
    outside = tmp_path.parent / "private.txt"
    outside.write_text("private")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("OS does not permit test symlinks")
    tools, _ = file_tools(tmp_path)
    assert FileVerifier(tools).verify(acceptance(link))["status"] == "unverifiable"


def test_acceptance_only_first_question_is_not_spoken(tmp_path):
    pytest.importorskip("langgraph")
    from nexus.task_conversation import TaskConversation
    from nexus.voice import render_conversation_speech
    store = ExecutionStore(tmp_path / "runs.sqlite3")
    model = Model({"action": "ask_user", "question": "Should the file contain PRIVATE_CRITERION?"})
    runner = PersistentExecutor(store, ExecutionRuntime(registry(Mock()), model))
    result = runner.start("test", acceptance=acceptance(tmp_path / "private.txt", "contains", value="PRIVATE_CRITERION"))
    response = TaskConversation(store, Mock(), run_id=result["run_id"]).handle("status")
    assert "PRIVATE_CRITERION" in response["result"]["task"]["question"]
    assert "PRIVATE_CRITERION" not in render_conversation_speech(response)
