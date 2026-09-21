import json
from unittest.mock import Mock

import pytest


def test_missing_and_invalid_usage():
    from nexus.execution_metrics import normalize_usage
    assert normalize_usage(None)["total_tokens"] is None
    for value in [True, -1, "2", 2**64]:
        assert normalize_usage({"prompt_tokens": value, "completion_tokens": 2})["status"] == "invalid"
    assert normalize_usage({"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 6})["status"] == "invalid"


def test_cost_requires_complete_supported_usage():
    from nexus.execution_metrics import normalize_usage, estimate_cost
    price = {"model": "test", "currency": "USD", "effective_date": "2026-09-20",
             "input_per_million": "1", "output_per_million": "2"}
    usage = normalize_usage({"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150})
    assert estimate_cost(usage, price, model="test")["amount"] == "0.0002"
    assert estimate_cost(usage, price, model="other")["amount"] is None
    usage = normalize_usage({"prompt_tokens": 100, "completion_tokens": 50, "extra_billing": 3})
    assert estimate_cost(usage, price, model="test")["amount"] is None


def test_recovery_counts_unknown_once():
    from nexus.execution_metrics import new_metrics, begin_attempt, recover_pending, project_metrics
    metrics = new_metrics()
    begin_attempt(metrics, "model")
    recover_pending(metrics)
    recover_pending(metrics)
    view = project_metrics({"metrics": metrics})
    assert view["model_attempts"] == 1
    assert view["model_unknown"] == 1
    assert view["usage"]["coverage"] == "unavailable"
    assert project_metrics({})["coverage"] == "legacy_unavailable"


def test_runtime_counts_without_changing_evidence(tmp_path):
    pytest.importorskip("langgraph")
    from nexus.execution_metrics import project_metrics
    from test_execution_store import executor, registry, Model, CALL
    runner = executor(tmp_path, registry(Mock(return_value={}), "allow"),
                      Model(CALL, {"action": "finish", "summary": "done", "evidence": [1]}))
    state = runner.start("test")
    counts = project_metrics(state)
    assert counts["model_attempts"] == 2
    assert counts["model_responses"] == 2
    assert counts["tool_dispatch_attempts"] == 1
    assert state["observations"][0]["number"] == 1


def test_quota_denial_prevents_model_attempt():
    pytest.importorskip("langgraph")
    from nexus.execution_runtime import ExecutionRuntime
    from nexus.execution_metrics import project_metrics
    from test_execution_store import registry
    model = Mock()
    result = ExecutionRuntime(registry(Mock(), "allow"), model, before_model=lambda: False).run("test")
    assert result["status"] == "budget_exhausted"
    assert project_metrics(result)["model_attempts"] == 0
    model.generate.assert_not_called()


def test_usage_ledger_rejects_extra_provider_data():
    from nexus.execution_metrics import begin_attempt, finish_attempt, new_metrics
    metrics = new_metrics()
    key = begin_attempt(metrics, "model")
    finish_attempt(metrics, key, "response", usage={"secret": "not-for-report"})
    assert metrics["attempts"][0]["usage"]["status"] == "invalid"
    assert "not-for-report" not in json.dumps(metrics)


@pytest.mark.parametrize("detail", [{"cached_tokens": 1}, {"reasoning_tokens": 1}, {"unknown": 0}])
def test_unsupported_billing_is_not_estimated(detail):
    from nexus.execution_metrics import normalize_usage
    result = normalize_usage({"prompt_tokens": 2, "completion_tokens": 1, "completion_tokens_details": detail})
    assert result["status"] == "available"
    assert result["billing_supported"] is False


def test_pending_tool_recovery_never_replays_or_double_counts(tmp_path):
    pytest.importorskip("langgraph")
    from nexus.execution_metrics import project_metrics
    from test_execution_store import executor, registry, Model, CALL
    handler = Mock(return_value={})
    runner = executor(tmp_path, registry(handler, "allow"), Model(CALL))
    original = runner.store.save
    def crash(state):
        if state.get("observations"):
            raise OSError("Crash before result checkpoint")
        original(state)
    runner.store.save = crash
    with pytest.raises(OSError):
        runner.start("test")
    resumed = executor(tmp_path, registry(handler, "allow"), Model(CALL))
    key = resumed.store.list()[0]["run_id"]
    for _ in range(2):
        state = resumed.resume(key)
        assert state["status"] == "needs_review"
        assert project_metrics(state)["tool_outcomes"] == {"unknown": 1}
    handler.assert_called_once()
