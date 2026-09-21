import json
from unittest.mock import Mock

import pytest


def test_catalog_and_live_selection():
    from nexus.evaluation_cases import case_catalog, select_cases
    cases = case_catalog()
    assert len(cases) == 17
    assert len(select_cases("live")) == 3
    assert all(c["split"] == "development" for c in select_cases("live"))
    cases[0]["id"] = "changed"
    assert case_catalog()[0]["id"] != "changed"
    for ids in [["missing"], ["project-1", "project-1"]]:
        with pytest.raises(ValueError):
            select_cases("offline", ids)


def test_all_offline_cases_use_real_executor(tmp_path):
    pytest.importorskip("langgraph")
    from nexus.evaluation_cases import case_catalog, execute_case
    for case in case_catalog():
        root = tmp_path / case["id"]
        result = execute_case(case, root)
        assert result["expected_behavior"]["status"] == "passed", (case["id"], result)
        assert result["state"]["persistence"] == "sqlite"


def test_offline_runner_never_constructs_provider(tmp_path):
    pytest.importorskip("langgraph")
    from nexus.execution_evaluation import EvaluationRunner, EvaluationStore
    provider = Mock(side_effect=AssertionError("provider constructed"))
    report = EvaluationRunner(tmp_path, model_factory=provider).run()
    assert report["mode"] == "offline"
    assert len(report["cases"]) == 17
    assert report["summary"]["normal_behavior"]["passed"] == 9
    assert report["summary"]["fault_behavior"]["passed"] == 8
    provider.assert_not_called()
    assert EvaluationStore(tmp_path).read(report["evaluation_id"])["status"] == "complete"


def test_zero_denominator_is_not_success():
    from nexus.execution_evaluation import summarize_cases
    assert summarize_cases([])["normal_behavior"]["rate"] is None


def test_offline_has_no_network(tmp_path, monkeypatch):
    import socket
    import urllib.request
    from nexus.execution_evaluation import EvaluationRunner
    blocked = Mock(side_effect=AssertionError("Network attempted"))
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    report = EvaluationRunner(tmp_path).run()
    assert report["status"] == "complete"
    blocked.assert_not_called()


def test_report_limits_escaping_and_preserves_previous_json(tmp_path):
    from nexus.execution_evaluation import EvaluationRunner, EvaluationStore, render_report
    report = EvaluationRunner(tmp_path).run(case_ids=["false-finish"])
    store = EvaluationStore(tmp_path)
    key = report["evaluation_id"]
    report = store.review(key, case_id="false-finish", verdict="partial", note="<script>bad</script> [click](https://invalid.example)")
    markdown = render_report(report)
    assert "<script>" not in markdown and "[click](" not in markdown
    before = (store.directory(key) / "report.json").read_bytes()
    report["cases"][0]["summary"] = "x" * (1024 * 1024)
    with store.locked(key), pytest.raises(ValueError):
        store.save_locked(report)
    assert (store.directory(key) / "report.json").read_bytes() == before


def test_budget_is_saved_before_provider_and_errors_not_refunded(tmp_path):
    from nexus.execution_evaluation import EvaluationRunner
    class BrokenModel:
        def generate(self, *args, **kwargs):
            reports = list((tmp_path / "evaluations").glob("*/report.json"))
            assert json.loads(reports[0].read_text())["calls_reserved"] == 1
            raise RuntimeError("private provider detail")
    report = EvaluationRunner(tmp_path, model_factory=BrokenModel,
        model_identity={"provider": "test", "model": "fake", "tier": "simple"}).run(mode="live", max_calls=1)
    assert report["calls_reserved"] == 1
    assert report["cases"][0]["metrics"]["model_errors"] == 1
    assert report["cases"][1]["status"] == "skipped"
    assert "private provider detail" not in json.dumps(report)


def test_report_symlink_is_rejected(tmp_path):
    from nexus.execution_evaluation import EvaluationRunner, EvaluationStore
    report = EvaluationRunner(tmp_path).run(case_ids=["false-finish"])
    store = EvaluationStore(tmp_path)
    target = store.directory(report["evaluation_id"]) / "report.md"
    target.unlink()
    external = tmp_path / "external.md"
    external.write_text("untouched")
    try:
        target.symlink_to(external)
    except OSError:
        pytest.skip("OS does not permit symlinks")
    with store.locked(report["evaluation_id"]), pytest.raises(ValueError):
        store.save_locked(report)
    assert external.read_text() == "untouched"


def test_atomic_failure_preserves_json(tmp_path, monkeypatch):
    import nexus.execution_evaluation as evaluation
    report = evaluation.EvaluationRunner(tmp_path).run(case_ids=["false-finish"])
    store = evaluation.EvaluationStore(tmp_path)
    path = store.directory(report["evaluation_id"]) / "report.json"
    previous = path.read_bytes()
    monkeypatch.setattr(evaluation.os, "replace", Mock(side_effect=OSError("disk error")))
    with pytest.raises(OSError):
        store.review(report["evaluation_id"], case_id="false-finish", verdict="passed", note="Review")
    assert path.read_bytes() == previous


def test_report_lock_rejects_concurrent_review(tmp_path):
    from nexus.execution_evaluation import EvaluationRunner, EvaluationStore
    report = EvaluationRunner(tmp_path).run(case_ids=["false-finish"])
    store = EvaluationStore(tmp_path)
    with store.locked(report["evaluation_id"]), pytest.raises(RuntimeError):
        store.review(report["evaluation_id"], case_id="false-finish", verdict="passed", note="Review")
    assert store.read(report["evaluation_id"])["cases"][0]["reviews"] == []


def test_suite_deadline_skips_without_model_construction(tmp_path):
    from nexus.execution_evaluation import EvaluationRunner
    factory = Mock(side_effect=AssertionError("Must not construct"))
    ticks = iter([0, 301, 302, 303])
    report = EvaluationRunner(tmp_path, clock=lambda: next(ticks), model_factory=factory,
        model_identity={"provider": "test", "model": "fake", "tier": "simple"}).run(mode="live", max_calls=5)
    assert report["status"] == "incomplete"
    assert report["summary"]["normal_behavior"]["rate"] is None
    assert report["calls_reserved"] == 0
    factory.assert_not_called()


def test_corrupted_report_is_rejected(tmp_path):
    from nexus.execution_evaluation import EvaluationRunner, EvaluationStore
    report = EvaluationRunner(tmp_path).run(case_ids=["false-finish"])
    store = EvaluationStore(tmp_path)
    report["cases"][0]["reviews"] = [{"verdict": "passed", "note": None}]
    (store.directory(report["evaluation_id"]) / "report.json").write_text(json.dumps(report))
    with pytest.raises(ValueError):
        store.read(report["evaluation_id"])


def test_keyboard_interrupt_does_not_start_next_live_case(tmp_path):
    from nexus.execution_evaluation import EvaluationRunner
    model = Mock()
    model.generate.side_effect = KeyboardInterrupt()
    report = EvaluationRunner(tmp_path, model_factory=lambda: model,
        model_identity={"provider": "test", "model": "fake", "tier": "simple"}).run(mode="live", max_calls=5)
    assert report["status"] == "interrupted"
    assert report["calls_reserved"] == 1
    assert report["cases"][1]["status"] == "not_started"
    model.generate.assert_called_once()


def test_live_call_budget_and_human_review(tmp_path):
    pytest.importorskip("langgraph")
    from nexus.execution_evaluation import EvaluationRunner, EvaluationStore
    from nexus.evaluation_cases import ScriptedModel
    model = ScriptedModel([{"action": "ask_user", "question": "Which material?"}])
    report = EvaluationRunner(tmp_path, model_factory=lambda: model,
        model_identity={"provider": "test", "model": "fake", "tier": "simple"}).run(mode="live", max_calls=1)
    assert report["calls_reserved"] == 1
    assert report["cases"][0]["status"] == "needs_intervention"
    assert report["cases"][1]["status"] == "skipped"
    store = EvaluationStore(tmp_path)
    updated = store.review(report["evaluation_id"], case_id="project-1", verdict="partial", note="Needs more sources")
    assert updated["cases"][0]["human_assessment"] == "partial"
    assert updated["cases"][0]["expected_behavior"] == report["cases"][0]["expected_behavior"]
    with pytest.raises(ValueError):
        store.read("../escape")
