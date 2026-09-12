import json
import os
import subprocess
import sys
from unittest.mock import Mock

import pytest

from nexus.execution_runtime import ExecutionRuntime
from nexus.execution_store import ExecutionStore, PersistentExecutor
from nexus.execution_tools import ToolContract, ToolRegistry


CALL = {"action": "tool", "tool": "act", "arguments": {}, "summary": "Act once"}


class Model:
    def __init__(self, *actions):
        self.actions = iter(actions)
        self.prompts = []

    def generate(self, system, prompt, **kwargs):
        self.prompts.append(json.loads(prompt))
        return json.dumps(next(self.actions))


def registry(handler, policy="ask", config=None):
    result = ToolRegistry()
    result.register(ToolContract("act", "Test action", {"type": "object", "additionalProperties": False},
                                 {"type": "object"}, side_effects="external"), handler, lambda: policy,
                    binding=lambda: config)
    return result


def executor(tmp_path, tools, model):
    pytest.importorskip("langgraph")
    return PersistentExecutor(ExecutionStore(tmp_path / "executor.sqlite3"), ExecutionRuntime(tools, model))


def test_approval_resume_reopens_store_and_executes_once(tmp_path):
    handler = Mock(return_value={"done": True})
    tools = registry(handler)
    first = executor(tmp_path, tools, Model(CALL)).start("Act")
    assert first["status"] == "waiting_approval"
    handler.assert_not_called()
    second = executor(tmp_path, tools, Model({"action": "finish", "summary": "Done", "evidence": [2]}))
    with pytest.raises(ValueError):
        second.resume(first["run_id"], approval_token="wrong")
    result = second.resume(first["run_id"], approval_token=first["approval_token"])
    assert result["status"] == "reported_complete"
    assert result["steps"] == 2
    assert result["persistence"] == "sqlite"
    handler.assert_called_once_with({}, True)
    with pytest.raises(ValueError):
        second.resume(first["run_id"])


def test_changed_config_invalidates_approval(tmp_path):
    config = {"target": "old"}
    handler = Mock(return_value={})
    runner = executor(tmp_path, registry(handler, config=config), Model(CALL))
    first = runner.start("Act")
    config["target"] = "new"
    with pytest.raises(ValueError, match="configuration changed"):
        runner.resume(first["run_id"], approval_token=first["approval_token"])
    assert runner.store.get(first["run_id"])["approval_binding"] != first["approval_binding"]
    handler.assert_not_called()


def test_answer_and_budget_survive_resume(tmp_path):
    runner = executor(tmp_path, registry(Mock()), Model({"action": "ask_user", "question": "Which file?"}))
    first = runner.start("Act", max_steps=2)
    runner.runtime.model = Model({"action": "ask_user", "question": "Anything else?"})
    second = runner.resume(first["run_id"], answer="report.txt")
    assert runner.runtime.model.prompts[0]["user_answers"] == ["report.txt"]
    assert second["steps"] == 2
    assert runner.resume(first["run_id"], answer="No")["status"] == "budget_exhausted"


@pytest.mark.parametrize("operation,status", [("pause", "paused"), ("cancel", "cancelled")])
def test_control_during_tool_keeps_result(tmp_path, operation, status):
    def handler(args, approved):
        run_id = runner.store.list()[0]["run_id"]
        runner.store.request(run_id, operation)
        return {"done": True}

    runner = executor(tmp_path, registry(handler, "allow"), Model(CALL))
    state = runner.start("Act")
    assert state["status"] == status
    assert state["observations"][0]["data"] == {"done": True}
    assert state["pending_action"] is None
    if operation == "cancel":
        with pytest.raises(ValueError):
            runner.resume(state["run_id"])
    else:
        runner.runtime.model = Model({"action": "finish", "summary": "Done", "evidence": [1]})
        assert runner.resume(state["run_id"])["status"] == "reported_complete"


def test_lease_excludes_second_runner(tmp_path):
    store = ExecutionStore(tmp_path / "executor.sqlite3")
    state = store.create({"goal": "Act", "status": "created"})
    with store.lease(state["run_id"]):
        with pytest.raises(RuntimeError, match="already running"):
            with store.lease(state["run_id"]):
                pytest.fail("Concurrent runner entered")
        store.request(state["run_id"], "cancel")
        store.save(state)
        assert store.get(state["run_id"])["control_requested"] == "cancel"


def test_process_crash_after_side_effect_is_not_replayed(tmp_path):
    pytest.importorskip("langgraph")
    script = '''
import os, sys, json
from pathlib import Path
from nexus.execution_store import ExecutionStore, PersistentExecutor
from nexus.execution_runtime import ExecutionRuntime
from nexus.execution_tools import ToolRegistry, ToolContract
root = Path(sys.argv[1])
class Model:
    def generate(self, *args, **kwargs):
        return json.dumps({"action":"tool","tool":"act","arguments":{},"summary":"Act"})
def handler(args, approved):
    (root / "effect.txt").write_text("performed")
    os._exit(37)
tools = ToolRegistry()
tools.register(ToolContract("act", "Action", {"type":"object","additionalProperties":False},
                            {"type":"object"}, side_effects="external"), handler, lambda:"allow")
PersistentExecutor(ExecutionStore(root / "executor.sqlite3"), ExecutionRuntime(tools, Model())).start("Act")
'''
    process = subprocess.run([sys.executable, "-c", script, str(tmp_path)], env=os.environ.copy(),
                             capture_output=True, timeout=40)
    assert process.returncode == 37, process.stderr.decode()
    assert (tmp_path / "effect.txt").read_text() == "performed"
    handler = Mock()
    runner = executor(tmp_path, registry(handler, "allow"), Model(CALL))
    run_id = runner.store.list()[0]["run_id"]
    assert runner.resume(run_id)["status"] == "needs_review"
    handler.assert_not_called()


def test_cli_status_does_not_construct_model_or_tools(tmp_path, monkeypatch, capsys):
    from nexus import cli
    import nexus.execution_tools as tools

    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    monkeypatch.setattr(tools, "build_tool_registry", Mock(side_effect=AssertionError("No tool access")))
    monkeypatch.setattr(sys, "argv", ["nexus", "executor", "runs"])
    cli.main()
    assert json.loads(capsys.readouterr().out) == {"runs": []}


@pytest.mark.parametrize("outcome", ["completed", "not-executed"])
def test_reconcile_never_executes_and_requires_fresh_approval(tmp_path, outcome):
    handler = Mock(side_effect=RuntimeError("uncertain"))
    runner = executor(tmp_path, registry(handler, "allow"), Model(CALL))
    first = runner.start("Act")
    assert first["status"] == "needs_review"
    resolved = runner.resolve(first["run_id"], outcome=outcome, note="Checked the actual destination")
    assert resolved["status"] == "paused"
    assert resolved["observations"][-1]["status"] == "user_reconciled"
    assert handler.call_count == 1
    if outcome == "not-executed":
        runner.runtime.registry = registry(handler, "ask")
        assert runner.resume(first["run_id"])["status"] == "waiting_approval"
        assert handler.call_count == 1
    else:
        runner.runtime.model = Model({"action": "finish", "summary": "Done", "evidence": [2]})
        assert runner.resume(first["run_id"])["status"] == "invalid_completion"


def test_approval_token_cannot_be_used_on_another_run(tmp_path):
    handler = Mock()
    runner = executor(tmp_path, registry(handler), Model(CALL, CALL))
    first = runner.start("First")
    second = runner.start("Second")
    with pytest.raises(ValueError):
        runner.resume(second["run_id"], approval_token=first["approval_token"])
    handler.assert_not_called()


def test_cancellation_while_waiting_does_not_need_approval(tmp_path):
    handler = Mock()
    runner = executor(tmp_path, registry(handler), Model(CALL))
    state = runner.start("Act")
    runner.store.request(state["run_id"], "cancel")
    assert runner.resume(state["run_id"])["status"] == "cancelled"
    handler.assert_not_called()


def test_checkpoint_failure_before_dispatch_prevents_tool(tmp_path):
    handler = Mock()
    runner = executor(tmp_path, registry(handler, "allow"), Model(CALL))
    save = runner.store.save

    def fail_before_call(state):
        if state.get("phase") == "tool_running":
            raise OSError("Disk unavailable")
        save(state)

    runner.store.save = fail_before_call
    with pytest.raises(OSError):
        runner.start("Act")
    handler.assert_not_called()


def test_deadline_is_cumulative_not_wall_time_waiting_for_user(tmp_path):
    tick = [0.0]
    runner = executor(tmp_path, registry(Mock()), Model({"action": "ask_user", "question": "Which?"}))
    runner.runtime.clock = lambda: tick[0]
    original = runner.runtime.model.generate

    def slow(*args, **kwargs):
        tick[0] += 2
        return original(*args, **kwargs)

    runner.runtime.model.generate = slow
    state = runner.start("Act", timeout_seconds=3)
    assert state["elapsed_seconds"] == 2
    tick[0] = 1000
    runner.runtime.model = Model({"action": "ask_user", "question": "Again?"})
    resumed = runner.resume(state["run_id"], answer="Here")
    assert resumed["status"] == "waiting_input"
    assert resumed["elapsed_seconds"] == 2


def test_interrupt_remains_cancelled_after_manual_reconciliation(tmp_path):
    runner = executor(tmp_path, registry(Mock(side_effect=KeyboardInterrupt), "allow"), Model(CALL))
    state = runner.start("Act")
    assert state["status"] == "cancelled"
    resolved = runner.resolve(state["run_id"], outcome="completed", note="Verified manually")
    assert resolved["status"] == "cancelled"
    with pytest.raises(ValueError):
        runner.resume(state["run_id"])


def test_pause_during_model_response_prevents_dispatch(tmp_path):
    handler = Mock()
    runner = executor(tmp_path, registry(handler, "allow"), Model(CALL))
    generate = runner.runtime.model.generate

    def request_pause(*args, **kwargs):
        runner.store.request(runner.store.list()[0]["run_id"], "pause")
        return generate(*args, **kwargs)

    runner.runtime.model.generate = request_pause
    state = runner.start("Act")
    assert state["status"] == "paused"
    assert state["control_requested"] == "pause"
    handler.assert_not_called()


def test_restart_after_committed_success_does_not_repeat_write(tmp_path):
    handler = Mock(return_value={"done": True})
    runner = executor(tmp_path, registry(handler, "allow"), Model(CALL))
    save = runner.store.save

    def simulate_exit(state):
        save(state)
        if state.get("phase") == "idle" and state["observations"]:
            raise OSError("Simulated process exit after committing observation")

    runner.store.save = simulate_exit
    with pytest.raises(OSError):
        runner.start("Act")
    resumed = executor(tmp_path, registry(handler, "allow"),
                       Model({"action": "finish", "summary": "Done", "evidence": [1]}))
    run_id = resumed.store.list()[0]["run_id"]
    assert resumed.resume(run_id)["status"] == "reported_complete"
    assert handler.call_count == 1
