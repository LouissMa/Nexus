from unittest.mock import Mock

import pytest

from nexus.execution_tools import ToolContract, ToolRegistry, build_tool_registry


def contract(**overrides):
    return ToolContract(**{
        "name": "test.read", "description": "Read a test value.",
        "input_schema": {"type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"], "additionalProperties": False},
        "output_schema": {"type": "object", "required": ["value"], "properties": {"value": {"type": "integer"}}, "additionalProperties": False},
        "side_effects": "none", "idempotent": True, **overrides,
    })


def test_invalid_arguments_never_dispatch():
    registry, handler = ToolRegistry(), Mock()
    registry.register(contract(), handler, lambda: "allow")
    for arguments in ({}, {"value": True}, {"value": 1, "extra": 2}):
        assert registry.call("test.read", arguments)["status"] == "invalid_arguments"
    handler.assert_not_called()


def test_approval_and_revocation_are_checked_every_call():
    registry, handler = ToolRegistry(), Mock(return_value={"value": 1})
    policy = ["ask"]
    registry.register(contract(side_effects="external", idempotent=False), handler, lambda: policy[0])
    assert registry.call("test.read", {"value": 1})["status"] == "approval_required"
    handler.assert_not_called()
    assert registry.call("test.read", {"value": 1}, approved=True)["status"] == "success"
    policy[0] = "deny"
    assert registry.call("test.read", {"value": 1}, approved=True)["status"] == "denied"
    assert handler.call_count == 1


def test_result_validation_and_errors_do_not_repeat_side_effects():
    registry, handler = ToolRegistry(), Mock(return_value={"value": "wrong"})
    registry.register(contract(side_effects="external", idempotent=False), handler, lambda: "allow")
    result = registry.call("test.read", {"value": 1})
    assert result["status"] == "invalid_result"
    assert result["effect_outcome"] == "unknown"
    assert handler.call_count == 1
    handler.side_effect = RuntimeError("secret-example-api-key")
    result = registry.call("test.read", {"value": 1})
    assert result["status"] == "failed"
    assert "secret-example" not in str(result)


def test_contract_is_copied_and_catalog_is_isolated():
    registry = ToolRegistry()
    original = contract()
    registry.register(original, lambda args, approved: args, lambda: "allow")
    original.input_schema["required"] = []
    catalog = registry.catalog()
    catalog[0]["input_schema"]["required"] = []
    assert registry.call("test.read", {})["status"] == "invalid_arguments"
    with pytest.raises(ValueError):
        registry.register(contract(), Mock(), lambda: "allow")


def test_remote_schema_refs_are_rejected():
    with pytest.raises(ValueError):
        ToolRegistry().register(contract(input_schema={"$ref": "https://example.com/schema"}), Mock(), lambda: "allow")


def test_unknown_tool_and_oversized_output():
    registry = ToolRegistry()
    assert registry.call("unknown", {})["status"] == "unknown_tool"
    registry.register(contract(output_schema={"type": "object"}), lambda args, approved: {"text": "x" * 70000}, lambda: "allow")
    assert registry.call("test.read", {"value": 1})["status"] == "result_too_large"


def test_existing_filesystem_adapter_and_disabled_config(tmp_path):
    from nexus.integrations.manager import build_tool_manager
    from nexus.automation import AutomationManager

    (tmp_path / "note.txt").write_text("hello")
    settings = {"filesystem": {"enabled": True, "roots": [str(tmp_path)], "allowed_operations": ["read", "search", "list"]}}
    tools = build_tool_manager(settings, tmp_path / "audit")
    automations = AutomationManager({}, tmp_path, Mock())
    registry = build_tool_registry(tools=tools, automations=automations)
    result = registry.call("filesystem.read", {"path": str(tmp_path / "note.txt")})
    assert result["status"] == "success"
    assert result["data"]["content"] == "hello"
    settings["filesystem"]["enabled"] = False
    assert registry.call("filesystem.read", {"path": str(tmp_path / "note.txt")}, approved=True)["status"] == "denied"


def test_automation_policy_is_preserved_and_catalog_hides_paths(tmp_path):
    from nexus.automation import AutomationManager

    opener = Mock(return_value=True)
    manager = AutomationManager({"web": {"type": "browser", "url": "https://example.com/?secret=private", "allowed_hosts": ["example.com"], "policy": "ask"}}, tmp_path, Mock(), browser_opener=opener)
    tools = Mock(settings={})
    registry = build_tool_registry(tools=tools, automations=manager)
    assert "private" not in str(registry.catalog())
    assert registry.call("automation.web", {})["status"] == "approval_required"
    opener.assert_not_called()
    assert registry.call("automation.web", {}, approved=True)["status"] == "success"
    opener.assert_called_once()


def test_executor_cli_end_to_end(tmp_path, monkeypatch, capsys):
    import json
    import sys
    from nexus import cli
    from nexus.config import update_tool_settings

    monkeypatch.setenv("NEXUS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("NEXUS_FILESYSTEM_ROOTS", raising=False)
    (tmp_path / "note.txt").write_text("hello world")
    update_tool_settings("filesystem", {"roots": [str(tmp_path)]})
    monkeypatch.setattr(sys, "argv", ["nexus", "executor", "tools"])
    cli.main()
    catalog = json.loads(capsys.readouterr().out)["tools"]
    assert {item["name"] for item in catalog} == {"filesystem.list", "filesystem.read", "filesystem.search"}
    args = json.dumps({"path": str(tmp_path / "note.txt"), "max_bytes": 5})
    monkeypatch.setattr(sys, "argv", ["nexus", "executor", "call", "filesystem.read", "--arguments", args])
    cli.main()
    result = json.loads(capsys.readouterr().out)
    assert result["data"]["content"] == "hello"
    assert result["data"]["truncated"] is True


def test_nested_ref_and_nonfinite_inputs_rejected():
    schema = {"type": "object", "properties": {"value": {"$ref": "https://example.com/secret"}}, "additionalProperties": False}
    with pytest.raises(ValueError):
        ToolRegistry().register(contract(input_schema=schema), Mock(), lambda: "allow")
    registry = ToolRegistry()
    handler = Mock()
    registry.register(contract(), handler, lambda: "allow")
    assert registry.call("test.read", {"value": float("nan")})["status"] == "invalid_arguments"
    handler.assert_not_called()
