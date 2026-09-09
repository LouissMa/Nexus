import json
from unittest.mock import Mock

import pytest

from nexus.execution_tools import ToolContract, ToolRegistry
from nexus.execution_runtime import ExecutionRuntime


class Model:
    def __init__(self, *actions):
        self.actions = iter(actions)
        self.prompts = []

    def generate(self, system, prompt, **kwargs):
        self.prompts.append(json.loads(prompt))
        return json.dumps(next(self.actions))


def tool(name="read", policy="allow", effect="none", handler=None):
    registry = ToolRegistry()
    registry.register(ToolContract(name, "Read input", {"type": "object", "properties": {}, "additionalProperties": False},
                                   {"type": "object"}, side_effects=effect, idempotent=effect == "none"),
                      handler or (lambda args, approved: {"value": "observed evidence"}), lambda: policy)
    return registry


CALL = {"action": "tool", "tool": "read", "arguments": {}, "summary": "Read evidence"}
FINISH = {"action": "finish", "summary": "Report from evidence", "evidence": [1]}


def test_observation_drives_next_model_action():
    pytest.importorskip("langgraph")
    model = Model(CALL, FINISH)
    result = ExecutionRuntime(tool(), model).run("Review the input")
    assert result["status"] == "reported_complete"
    assert result["verification"] == "tool_references_only"
    assert model.prompts[1]["observations"][0]["data"]["value"] == "observed evidence"


def test_approval_stops_before_side_effect():
    pytest.importorskip("langgraph")
    handler = Mock()
    result = ExecutionRuntime(tool(policy="ask", effect="external", handler=handler), Model(CALL)).run("Open something")
    assert result["status"] == "waiting_approval"
    assert result["pending_action"]["tool"] == "read"
    handler.assert_not_called()


def test_uncertain_effect_stops_without_retry():
    pytest.importorskip("langgraph")
    handler = Mock(side_effect=RuntimeError("secret"))
    result = ExecutionRuntime(tool(effect="external", handler=handler), Model(CALL)).run("Act")
    assert result["status"] == "needs_review"
    assert handler.call_count == 1
    assert "secret" not in json.dumps(result)


def test_finish_requires_successful_evidence():
    pytest.importorskip("langgraph")
    result = ExecutionRuntime(tool(), Model(FINISH)).run("Review")
    assert result["status"] == "invalid_completion"


def test_repeated_read_and_step_limits():
    pytest.importorskip("langgraph")
    model = Model(CALL, CALL, CALL)
    assert ExecutionRuntime(tool(), model).run("Read repeatedly")["status"] == "repeated_action"
    assert ExecutionRuntime(tool(), Model(CALL)).run("Read", max_steps=1)["status"] == "budget_exhausted"


def test_model_cannot_supply_approval():
    pytest.importorskip("langgraph")
    handler = Mock()
    result = ExecutionRuntime(tool(handler=handler), Model({**CALL, "approved": True})).run("Read", max_steps=1)
    assert result["status"] == "budget_exhausted"
    handler.assert_not_called()


def test_clarification_and_failed_read_recovery():
    pytest.importorskip("langgraph")
    question = {"action": "ask_user", "question": "Which directory?"}
    assert ExecutionRuntime(tool(), Model(question)).run("Find files")["status"] == "waiting_input"
    handler = Mock(side_effect=[RuntimeError("offline"), {"value": "recovered"}])
    result = ExecutionRuntime(tool(handler=handler), Model(CALL, CALL, {**FINISH, "evidence": [2]})).run("Read")
    assert result["status"] == "reported_complete"
    assert handler.call_count == 2


def test_langgraph_interrupt_resume_does_not_replay_previous_node():
    pytest.importorskip("langgraph")
    from langgraph.graph import StateGraph, START, END
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import interrupt, Command

    executed = []
    graph = StateGraph(dict)
    graph.add_node("prepare", lambda state: (executed.append("prepare") or state))
    graph.add_node("approval", lambda state: {"approved": interrupt({"action": "test"})})
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "approval")
    graph.add_edge("approval", END)
    app = graph.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "smoke"}}
    assert app.invoke({}, config)["__interrupt__"]
    assert app.invoke(Command(resume=True), config)["approved"] is True
    assert executed == ["prepare"]


def test_deadline_expires_before_tool_dispatch():
    pytest.importorskip("langgraph")
    tick = [0.0]
    model = Model(CALL)
    generate = model.generate

    def slow(*args, **kwargs):
        tick[0] = 10.0
        return generate(*args, **kwargs)

    model.generate = slow
    handler = Mock()
    result = ExecutionRuntime(tool(handler=handler), model, clock=lambda: tick[0]).run("Read", timeout_seconds=1)
    assert result["status"] == "budget_exhausted"
    handler.assert_not_called()


def test_interrupt_during_tool_retains_uncertain_action():
    pytest.importorskip("langgraph")
    handler = Mock(side_effect=KeyboardInterrupt)
    result = ExecutionRuntime(tool(effect="external", handler=handler), Model(CALL)).run("Act")
    assert result["status"] == "cancelled"
    assert result["observations"][0]["effect_outcome"] == "unknown"
    assert result["pending_action"]["tool"] == "read"


def test_unknown_tool_is_feedback_not_execution():
    pytest.importorskip("langgraph")
    handler = Mock(return_value={"value": 1})
    unknown = {**CALL, "tool": "arbitrary_shell"}
    result = ExecutionRuntime(tool(handler=handler), Model(unknown, CALL, {**FINISH, "evidence": [2]})).run("Read")
    assert result["status"] == "reported_complete"
    assert result["observations"][0]["status"] == "unknown_tool"
    assert handler.call_count == 1


def test_cli_dynamic_run_uses_configured_model_and_existing_filesystem(tmp_path, monkeypatch, capsys):
    pytest.importorskip("langgraph")
    import sys
    from nexus import cli
    from nexus.config import update_tool_settings

    monkeypatch.setenv("NEXUS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("NEXUS_FILESYSTEM_ROOTS", raising=False)
    (tmp_path / "note.txt").write_text("Read this project note")
    update_tool_settings("filesystem", {"roots": [str(tmp_path)]})
    call = {**CALL, "tool": "filesystem.read", "arguments": {"path": str(tmp_path / "note.txt")}}
    model = Model(call, FINISH)
    monkeypatch.setattr(cli.LLMConfig, "from_env", lambda **kwargs: Mock(is_configured=True))
    monkeypatch.setattr(cli, "OpenAICompatibleLLM", lambda config: model)
    monkeypatch.setattr(sys, "argv", ["nexus", "executor", "run", "Read and summarize the project note"])
    cli.main()
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "reported_complete"
    assert result["observations"][0]["data"]["content"] == "Read this project note"
