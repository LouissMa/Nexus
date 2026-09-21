import json
import sys
from unittest.mock import Mock

import pytest


def test_offline_cli_and_review_without_personal_config(tmp_path, monkeypatch, capsys):
    pytest.importorskip("langgraph")
    from nexus import cli
    import nexus.evaluation_cases  # Load the explicitly configured registry before replacing the default factory.
    import nexus.execution_tools as tools
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    forbidden = Mock(side_effect=AssertionError("Personal configuration was accessed"))
    monkeypatch.setattr(cli.LLMConfig, "from_env", forbidden)
    monkeypatch.setattr(cli, "load_embedding_settings", forbidden)
    monkeypatch.setattr(tools, "build_tool_registry", forbidden)
    monkeypatch.setattr(sys, "argv", ["nexus", "executor", "evaluate", "--case", "false-finish"])
    cli.main()
    report = json.loads(capsys.readouterr().out)
    key = report["evaluation_id"]
    assert report["cases"][0]["expected_behavior"]["status"] == "passed"
    for suffix in [["evaluation-show", key], ["evaluation-review", key, "--case", "false-finish",
                   "--verdict", "partial", "--note", "Manual check"]]:
        monkeypatch.setattr(sys, "argv", ["nexus", "executor", *suffix])
        cli.main()
        assert json.loads(capsys.readouterr().out)["evaluation_id"] == key
    forbidden.assert_not_called()


@pytest.mark.parametrize("options", [["--mode", "live"], ["--max-calls", "1"],
    ["--mode", "live", "--max-calls", "1", "--case", "unknown"], ["--model-tier", "simple"]])
def test_invalid_evaluation_options_do_not_construct_provider(tmp_path, monkeypatch, capsys, options):
    from nexus import cli
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    provider = Mock(side_effect=AssertionError("Provider loaded"))
    monkeypatch.setattr(cli.LLMConfig, "from_env", provider)
    monkeypatch.setattr(sys, "argv", ["nexus", "executor", "evaluate", *options])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    provider.assert_not_called()


def test_live_cli_requires_explicit_budget_and_uses_fake_model(tmp_path, monkeypatch, capsys):
    pytest.importorskip("langgraph")
    from nexus import cli
    from nexus.llm import LLMConfig
    from nexus.evaluation_cases import ScriptedModel
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    config = LLMConfig(api_key="test-placeholder", model="fake", provider="test")
    monkeypatch.setattr(cli.LLMConfig, "from_env", lambda **kw: config)
    monkeypatch.setattr(cli, "OpenAICompatibleLLM", lambda config: ScriptedModel([
        {"action": "ask_user", "question": "Clarify?"}]))
    monkeypatch.setattr(sys, "argv", ["nexus", "executor", "evaluate", "--mode", "live", "--max-calls", "1"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["calls_reserved"] == 1
    assert "may incur charges" in output.err
    assert "test-placeholder" not in output.out
