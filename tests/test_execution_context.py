import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from nexus.service import NexusService
from nexus.store import JsonStore


def setup_context(tmp_path):
    from nexus.execution_context import ExecutionContextBuilder

    service = NexusService(JsonStore(tmp_path / "state.json"))
    service.store.mutate(lambda s: s.update(
        goals=[{"id": "g1", "title": "Research", "description": "next step", "status": "active"}],
        memories=[{"id": "m1", "text": "research public evidence", "tags": [], "privacy": "shared",
                   "created_at": "2026-01-01T00:00:00+00:00"},
                  {"id": "m2", "text": "research PRIVATE_SENTINEL", "tags": [], "privacy": "private",
                   "created_at": "2026-01-01T00:00:00+00:00"}],
        research_projects=[{"id": "r1", "title": "Study", "objective": "Research question", "status": "active",
                            "questions": [{"id": "q1", "text": "Why?", "status": "open"}],
                            "notes": [{"text": "SECRET_NOTE"}], "sources": [], "experiments": []}]))
    return service, ExecutionContextBuilder(service)


def test_shared_only_projection_and_provenance(tmp_path):
    service, builder = setup_context(tmp_path)
    context = builder.build("research", goal_ids=["g1"], research_id="r1")
    encoded = json.dumps(context)
    assert "PRIVATE_SENTINEL" not in encoded and "SECRET_NOTE" not in encoded
    assert context["goals"][0]["id"] == "g1"
    assert context["memories"][0]["id"] == "m1"
    assert {r["kind"] for r in context["references"]} == {"goal", "memory", "research"}
    builder.validate(context)


def test_sensitive_scope_requires_explicit_consent(tmp_path):
    _, builder = setup_context(tmp_path)
    with pytest.raises(ValueError):
        builder.build("research", memory_scope="private")
    assert "PRIVATE_SENTINEL" in json.dumps(builder.build("research", memory_scope="private", allow_sensitive=True))


@pytest.mark.parametrize("change", ["private", "forgotten", "archived", "expired", "deleted", "edited"])
def test_resume_validation_blocks_changed_memory(tmp_path, change):
    service, builder = setup_context(tmp_path)
    context = builder.build("research")
    def mutate(state):
        memory = state["memories"][0]
        if change == "private":
            memory["privacy"] = "private"
        elif change in {"forgotten", "archived"}:
            memory["status"] = change
        elif change == "expired":
            memory["expires_at"] = "2000-01-01T00:00:00+00:00"
        elif change == "deleted":
            state["memories"].pop(0)
        else:
            memory["text"] += " changed"
    service.store.mutate(mutate)
    with pytest.raises(ValueError, match="context"):
        builder.validate(context)


def test_unknown_source_and_large_unicode_budget(tmp_path):
    service, builder = setup_context(tmp_path)
    with pytest.raises(ValueError):
        builder.build("research", goal_ids=["missing"])
    def enlarge(state):
        state["goals"] = [{"id": f"g{i}", "title": "研" * 2000, "description": "究" * 2000,
                           "status": "active"} for i in range(3)]
        state["memories"] = [{"id": f"m{i}", "text": "research " + "文" * 2000, "privacy": "shared",
                              "created_at": "2026-01-01T00:00:00+00:00"} for i in range(5)]
    service.store.mutate(enlarge)
    context = builder.build("research", goal_ids=["g0", "g1", "g2"], research_id="r1")
    assert len(json.dumps(context, ensure_ascii=False).encode()) <= 16384
    assert context["truncated"]
    builder.validate(context)


def test_retrieval_failure_is_sanitized(tmp_path):
    service, builder = setup_context(tmp_path)
    def fail(*args, **kwargs):
        raise RuntimeError("SECRET_PROVIDER_KEY")
    service.memory_retriever.retrieve_result = fail
    result = builder.build("research")
    assert result["memories"] == []
    assert result["degradations"] == ["memory_retrieval_unavailable"]
    assert "SECRET_PROVIDER_KEY" not in json.dumps(result)


def test_durable_context_reuse_and_stale_block_preserve_approval(tmp_path):
    pytest.importorskip("langgraph")
    from nexus.execution_runtime import ExecutionRuntime
    from nexus.execution_store import ExecutionStore, PersistentExecutor
    from test_execution_store import Model, registry, CALL
    service, builder = setup_context(tmp_path)
    model = Model(CALL)
    calls = []
    runner = PersistentExecutor(ExecutionStore(tmp_path / "runs.sqlite3"),
        ExecutionRuntime(registry(lambda *args: calls.append(1) or {}), model), context_builder=builder)
    state = runner.start("research", context_options={"goal_ids": ["g1"]})
    assert model.prompts[0]["background_context"] == state["context"]
    saved = deepcopy(state["context"])
    service.store.mutate(lambda s: s["memories"].append({"id": "new", "text": "research newest", "privacy": "shared"}))
    builder.validate(saved)
    service.store.mutate(lambda s: s["goals"][0].update(title="changed"))
    before = runner.store.get(state["run_id"])
    with pytest.raises(ValueError, match="context"):
        runner.resume(state["run_id"], approval_token=state["approval_token"])
    assert runner.store.get(state["run_id"]) == before
    assert calls == []


def test_cli_context_options_are_available():
    from nexus.cli import build_parser
    args = build_parser().parse_args(["executor", "run", "research", "--with-context", "--context-goal", "g1"])
    assert args.with_context and args.context_goal == ["g1"]


def test_cli_invalid_context_has_safe_actionable_error(tmp_path, monkeypatch, capsys):
    import sys
    from nexus import cli
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(sys, "argv", ["nexus", "executor", "run", "research", "--context-goal", "g1"])
    with pytest.raises(SystemExit):
        cli.main()
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "context_invalid"
    assert "--with-context" in result["error"]
    assert not (tmp_path / "home" / "executor.sqlite3").exists()


def test_untrusted_dense_hit_cannot_supply_private_or_forged_content(tmp_path):
    from nexus.rag import RetrievalResult
    service, builder = setup_context(tmp_path)
    def retrieve(memories, *args, **kwargs):
        assert all(m["privacy"] == "shared" for m in memories)
        return RetrievalResult([{"id": "m2", "text": "PRIVATE_SENTINEL"},
                                {"id": "m1", "text": "FORGED_TEXT", "retrieval_score": 1}],
                               {"strategy": "hybrid_dense_sparse", "error": "SECRET_ERROR"})
    service.memory_retriever.retrieve_result = retrieve
    context = builder.build("research")
    assert context["memories"][0]["text"] == "research public evidence"
    assert context["degradations"] == ["memory_dense_unavailable"]
    assert not any(s in json.dumps(context) for s in ["PRIVATE_SENTINEL", "FORGED_TEXT", "SECRET_ERROR"])


def test_expiry_is_rechecked_without_source_edit_even_when_pinned(tmp_path):
    service, builder = setup_context(tmp_path)
    now = datetime(2026, 9, 13, tzinfo=UTC)
    builder.clock = lambda: now
    service.store.mutate(lambda s: s["memories"][0].update(expires_at=(now + timedelta(seconds=1)).isoformat(), pinned=True))
    context = builder.build("research")
    now += timedelta(seconds=2)
    with pytest.raises(ValueError):
        builder.validate(context)
    assert builder.build("research")["memories"] == []


def test_resume_uses_snapshot_without_retrieving_again(tmp_path):
    pytest.importorskip("langgraph")
    from nexus.execution_runtime import ExecutionRuntime
    from nexus.execution_store import ExecutionStore, PersistentExecutor
    from test_execution_store import Model, registry
    service, builder = setup_context(tmp_path)
    model = Model({"action": "ask_user", "question": "Which step?"})
    runner = PersistentExecutor(ExecutionStore(tmp_path / "runs.sqlite3"),
        ExecutionRuntime(registry(lambda *args: {}), model), context_builder=builder)
    state = runner.start("research", context_options={})
    snapshot = deepcopy(state["context"])
    def unexpected_retrieval():
        raise AssertionError("Resume must not initialize retrieval")
    builder.retriever_factory = unexpected_retrieval
    model = Model({"action": "ask_user", "question": "Anything else?"})
    resumed = PersistentExecutor(ExecutionStore(tmp_path / "runs.sqlite3"),
        ExecutionRuntime(registry(lambda *args: {}), model), context_builder=builder)
    result = resumed.resume(state["run_id"], answer="First")
    assert result["context"] == snapshot == model.prompts[0]["background_context"]


def test_context_is_not_successful_execution_evidence(tmp_path):
    pytest.importorskip("langgraph")
    from nexus.execution_runtime import ExecutionRuntime
    from nexus.execution_store import ExecutionStore, PersistentExecutor
    from test_execution_store import Model, registry
    _, builder = setup_context(tmp_path)
    runner = PersistentExecutor(ExecutionStore(tmp_path / "runs.sqlite3"),
        ExecutionRuntime(registry(lambda *args: {}), Model({"action": "finish", "summary": "Done", "evidence": [1]})),
        context_builder=builder)
    assert runner.start("research", context_options={})["status"] == "invalid_completion"


def test_source_changed_during_model_call_blocks_tool(tmp_path):
    pytest.importorskip("langgraph")
    from nexus.execution_runtime import ExecutionRuntime
    from nexus.execution_store import ExecutionStore, PersistentExecutor
    from test_execution_store import Model, registry, CALL
    service, builder = setup_context(tmp_path)
    calls = []
    model = Model(CALL)
    generate = model.generate
    def change_source(*args, **kwargs):
        service.store.mutate(lambda s: s["memories"][0].update(privacy="private"))
        return generate(*args, **kwargs)
    model.generate = change_source
    runner = PersistentExecutor(ExecutionStore(tmp_path / "runs.sqlite3"),
        ExecutionRuntime(registry(lambda *args: calls.append(1) or {}, "allow"), model), context_builder=builder)
    with pytest.raises(ValueError):
        runner.start("research", context_options={})
    assert not calls


def test_cli_context_run_and_resume(tmp_path, monkeypatch, capsys):
    pytest.importorskip("langgraph")
    import sys
    from unittest.mock import Mock
    from nexus import cli
    from nexus.rag import MemoryRetriever
    from test_execution_store import Model, registry
    import nexus.execution_tools
    service, _ = setup_context(tmp_path)
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(cli.JsonStore, "from_env", lambda: service.store)
    monkeypatch.setattr(nexus.execution_tools, "build_tool_registry", lambda: registry(lambda *args: {}))
    monkeypatch.setattr(cli.LLMConfig, "from_env", lambda **kwargs: Mock(is_configured=True))
    monkeypatch.setattr(cli, "build_memory_retriever", lambda *args: MemoryRetriever())
    model = Model({"action": "ask_user", "question": "Which step?"}, {"action": "ask_user", "question": "What next?"})
    monkeypatch.setattr(cli, "OpenAICompatibleLLM", lambda config: model)
    monkeypatch.setattr(sys, "argv", ["nexus", "executor", "run", "research", "--with-context", "--context-research", "r1"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    first = json.loads(capsys.readouterr().out)
    monkeypatch.setattr(sys, "argv", ["nexus", "executor", "resume", first["run_id"], "--answer", "First"])
    with pytest.raises(SystemExit):
        cli.main()
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["context"] == first["context"]
    assert resumed["status"] == "waiting_input"


@pytest.mark.parametrize("budget", [{"max_steps": 0}, {"max_steps": 51}, {"timeout_seconds": 0}])
def test_invalid_budget_never_retrieves_or_creates_run(tmp_path, budget):
    from nexus.execution_runtime import ExecutionRuntime
    from nexus.execution_store import ExecutionStore, PersistentExecutor
    from test_execution_store import Model, registry
    service, builder = setup_context(tmp_path)
    retrievals = []
    builder.retriever_factory = lambda: retrievals.append("remote query") or service.memory_retriever
    runner = PersistentExecutor(ExecutionStore(tmp_path / "runs.sqlite3"),
        ExecutionRuntime(registry(lambda *args: {}), Model()), context_builder=builder)
    with pytest.raises(ValueError):
        runner.start("research", context_options={}, **budget)
    assert retrievals == []
    assert runner.store.list() == []
