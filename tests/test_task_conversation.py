import json
from unittest.mock import Mock

import pytest

from nexus.execution_store import ExecutionStore, PersistentExecutor
from nexus.execution_runtime import ExecutionRuntime
from test_execution_store import Model, registry, CALL


def task_store(tmp_path):
    return ExecutionStore(tmp_path / "runs.sqlite3")


def seed(store, goal="Test", status="paused"):
    return store.create({"goal": goal, "status": status, "steps": 0, "observations": [],
                         "pending_action": None, "summary": "", "max_steps": 12, "timeout_seconds": 120})


def router(store, factory=None, **kwargs):
    from nexus.task_conversation import TaskConversation
    return TaskConversation(store, factory or Mock(side_effect=AssertionError("No model should initialize")), **kwargs)


def test_session_survives_reopen_and_rejects_stale_selection(tmp_path):
    store = task_store(tmp_path)
    a, b = seed(store), seed(store)
    session = store.task_session("default")
    store.update_task_session("default", session["revision"], run_id=a["run_id"], candidates=[])
    with pytest.raises(ValueError):
        store.update_task_session("default", session["revision"], run_id=b["run_id"], candidates=[])
    assert task_store(tmp_path).task_session("default")["run_id"] == a["run_id"]


def test_no_implicit_latest_selection_and_stable_candidate_numbers(tmp_path):
    store = task_store(tmp_path)
    a, b = seed(store, "first"), seed(store, "second")
    chat = router(store)
    result = chat.handle("继续任务")
    assert result["intent"] == "task_select_required"
    ids = [c["run_id"] for c in result["result"]["candidates"]]
    seed(store, "newest")
    selected = chat.handle("选择任务 2")
    assert selected["result"]["task"]["run_id"] == ids[1]
    assert store.task_session("default")["run_id"] == ids[1]


def test_status_controls_never_initialize_model(tmp_path):
    store = task_store(tmp_path)
    state = seed(store)
    chat = router(store, run_id=state["run_id"])
    assert chat.handle("查看进度")["result"]["task"]["status"] == "paused"
    chat.handle("暂停任务")
    assert store.get(state["run_id"])["control_requested"] == "pause"
    chat.handle("取消任务")
    assert store.get(state["run_id"])["control_requested"] == "cancel"


def test_text_start_voice_style_answer_reuses_run(tmp_path):
    pytest.importorskip("langgraph")
    from nexus.conversation import ConversationService
    store = task_store(tmp_path)
    model = Model({"action": "ask_user", "question": "Which folder?"},
                  {"action": "ask_user", "question": "Anything else?"})
    factory = lambda: PersistentExecutor(store, ExecutionRuntime(registry(lambda *args: {}), model))
    text = ConversationService(None, task_router=router(store, factory))
    first = text.handle("开始任务：检查资料")
    run_id = first["result"]["task"]["run_id"]
    voice = ConversationService(None, task_router=router(task_store(tmp_path), factory))
    assert voice.handle("查看进度")["result"]["task"]["run_id"] == run_id
    answered = voice.handle("项目目录")
    assert answered["result"]["task"]["run_id"] == run_id
    assert store.get(run_id)["user_answers"] == ["项目目录"]
    assert len(store.list()) == 1


def test_affirmation_and_approve_flag_never_authorize(tmp_path):
    pytest.importorskip("langgraph")
    store = task_store(tmp_path)
    handler = Mock(return_value={})
    executor = PersistentExecutor(store, ExecutionRuntime(registry(handler), Model(CALL)))
    first = executor.start("Test")
    chat = router(store, run_id=first["run_id"])
    for text in ["好的", "yes", "继续任务", "批准任务"]:
        response = chat.handle(text)
        assert response["requires_approval"]
        assert first["approval_token"] not in json.dumps(response)
    assert chat.handle("继续任务", approved=True)["intent"] == "task_error"
    handler.assert_not_called()


def test_unrecognized_chat_never_starts_task(tmp_path):
    store = task_store(tmp_path)
    assert router(store).handle("我想聊聊天")["intent"] == "task_clarify"
    assert store.list() == []


def test_numbered_selection_rejects_another_interfaces_list(tmp_path):
    store = task_store(tmp_path)
    seed(store, "first")
    a, b = router(store), router(store)
    a.handle("list tasks")
    seed(store, "second")
    b.handle("list tasks")
    assert a.handle("select task 1")["intent"] == "task_error"
    assert store.task_session("default")["run_id"] is None


def test_new_process_number_requires_receipt(tmp_path):
    store = task_store(tmp_path)
    seed(store)
    router(store).handle("list tasks")
    assert router(store).handle("select task 1")["intent"] == "task_select_required"
    assert store.task_session("default")["run_id"] is None


def test_question_does_not_echo_tool_result_in_speech(tmp_path):
    from nexus.voice import render_conversation_speech
    store = task_store(tmp_path)
    state = seed(store, status="waiting_input")
    state.update(summary="PRIVATE_TOOL_RESULT: what next?",
                 observations=[{"status": "success", "data": "PRIVATE_TOOL_RESULT"}])
    store.save(state)
    result = router(store, run_id=state["run_id"]).handle("status")
    assert "PRIVATE_TOOL_RESULT" not in render_conversation_speech(result)
    assert result["result"]["task"]["question"] == state["summary"]


def test_cancel_waiting_approval_without_model(tmp_path):
    store = task_store(tmp_path)
    state = seed(store, status="waiting_approval")
    state.update(approval_token="TOKEN", pending_action=CALL, phase="tool_pending")
    store.save(state)
    chat = router(store, run_id=state["run_id"])
    result = chat.handle("cancel")
    assert result["result"]["task"]["status"] == "cancelled"
    assert not result["requires_approval"]
    assert "approval_token" not in store.get(state["run_id"])
    assert chat.handle("continue")["result"]["task"]["next_action"] == "none"


def test_numbered_selection_receipt_works_across_processes(tmp_path):
    store = task_store(tmp_path)
    state = seed(store)
    shown = router(store).handle("list tasks")["result"]
    receipt = shown["selection_revision"]
    result = router(store).handle(f"select task 1 @{receipt}")
    assert result["result"]["task"]["run_id"] == state["run_id"]
    assert router(store).handle(f"select task 1 @{receipt}")["intent"] == "task_error"


def test_bare_number_selects_candidate_not_pending_answer(tmp_path):
    store = task_store(tmp_path)
    first = seed(store, "first", status="waiting_input")
    second = seed(store, "second")
    chat = router(store, run_id=first["run_id"])
    chat.handle("list tasks")
    result = chat.handle("1")
    assert result["result"]["task"]["run_id"] == second["run_id"]
    assert store.get(first["run_id"]).get("user_answers", []) == []


def test_cancellation_during_approval_transition_is_acknowledged(tmp_path):
    pytest.importorskip("langgraph")
    store = task_store(tmp_path)
    tools = registry(Mock())
    original_call = tools.call
    def cancelling_call(*args, **kwargs):
        run_id = store.list()[0]["run_id"]
        store.request_task_control(run_id, "cancel")
        return original_call(*args, **kwargs)
    tools.call = cancelling_call
    result = PersistentExecutor(store, ExecutionRuntime(tools, Model(CALL))).start("Test")
    assert result["status"] == "cancelled"
    assert "approval_token" not in store.get(result["run_id"])


def test_cancel_active_tool_is_cooperative_and_unknown_outcome_preserved(tmp_path):
    store = task_store(tmp_path)
    state = seed(store, status="running")
    state.update(phase="tool_running", pending_action=CALL)
    store.save(state)
    chat = router(store, run_id=state["run_id"])
    with store.lease(state["run_id"]):
        result = chat.handle("cancel")["result"]["task"]
        assert result["status"] == "running"
        assert result["control_requested"] == "cancel"
    result = chat.handle("cancel")["result"]["task"]
    assert result["status"] == "needs_review"
    assert result["next_action"] == "manual_review"


@pytest.mark.parametrize("private_context", [True, False])
def test_initial_question_speech_respects_context(tmp_path, private_context):
    from nexus.voice import render_conversation_speech
    store = task_store(tmp_path)
    state = seed(store, status="waiting_input")
    state["summary"] = "Which folder?"
    if private_context:
        state["context"] = {}
    store.save(state)
    speech = render_conversation_speech(router(store, run_id=state["run_id"]).handle("status"))
    assert ("Which folder?" in speech) is not private_context


def test_start_binds_session_before_execution(tmp_path):
    pytest.importorskip("langgraph")
    store = task_store(tmp_path)
    observed = []
    def handler(*args):
        observed.append(store.task_session("default")["run_id"])
        return {}
    executor = PersistentExecutor(store, ExecutionRuntime(registry(handler, "allow"),
        Model(CALL, {"action": "finish", "summary": "Done", "evidence": [1]})))
    result = router(store, lambda: executor).handle("start task: Test")
    assert observed == [result["result"]["task"]["run_id"]]


def test_cli_task_status_skips_embedding_and_model(tmp_path, monkeypatch, capsys):
    import sys
    from nexus import cli
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "load_embedding_settings", Mock(side_effect=AssertionError("Embedding initialized")))
    monkeypatch.setattr(cli.LLMConfig, "from_env", Mock(side_effect=AssertionError("LLM initialized")))
    monkeypatch.setattr(sys, "argv", ["nexus", "ask", "查看进度", "--task-mode"])
    cli.main()
    assert json.loads(capsys.readouterr().out)["intent"] == "task_select_required"


def test_real_voice_turns_share_text_task_and_keep_approval_pending(tmp_path):
    pytest.importorskip("langgraph")
    from nexus.conversation import ConversationService
    from nexus.voice import VoiceService, TranscriptionResult
    from nexus.config import VoiceSettings
    from nexus.voice_session import run_voice_session
    from test_voice_session import Recorder
    store = task_store(tmp_path)
    handler = Mock(return_value={"raw": "PRIVATE_TOOL_RESULT"})
    executor = PersistentExecutor(store, ExecutionRuntime(registry(handler), Model(CALL,
        {"action": "ask_user", "question": "What next?"})))
    first = router(store, lambda: executor).handle("开始任务：处理资料")
    run_id = first["result"]["task"]["run_id"]
    token = store.get(run_id)["approval_token"]
    transcriber = Mock()
    transcriber.transcribe.side_effect = [TranscriptionResult(t, "fake", "fake") for t in ["查看进度", "好的", "继续任务"]]
    voice = VoiceService(settings=VoiceSettings(enabled=True), transcriber=transcriber, synthesizer=Mock(),
        conversation=ConversationService(None, task_router=router(task_store(tmp_path))))
    events, recorder = [], Recorder()
    result = run_voice_session(voice, recorder=recorder, max_turns=3, play=False, emit=events.append)
    assert result["reason"] == "turn_limit" and result["completed_turns"] == 3
    turns = [e for e in events if e["event"] == "turn"]
    assert all(t["conversation"]["result"]["task"]["run_id"] == run_id for t in turns)
    assert token not in json.dumps(events)
    handler.assert_not_called()
    assert all(not p.exists() for p in recorder.paths)
    executor.resume(run_id, approval_token=token)
    after = router(task_store(tmp_path)).handle("查看进度")
    assert after["result"]["task"]["successful_observations"] == 1
    assert "PRIVATE_TOOL_RESULT" not in json.dumps(after)
    handler.assert_called_once()


def test_voice_answer_continues_same_question(tmp_path):
    pytest.importorskip("langgraph")
    from nexus.conversation import ConversationService
    from nexus.voice import VoiceService, TranscriptionResult
    from nexus.config import VoiceSettings
    from nexus.voice_session import run_voice_session
    from test_voice_session import Recorder
    store = task_store(tmp_path)
    model = Model({"action": "ask_user", "question": "Which folder?"}, {"action": "ask_user", "question": "Which file?"})
    factory = lambda: PersistentExecutor(store, ExecutionRuntime(registry(lambda *args: {}), model))
    first = router(store, factory).handle("start task: inspect files")
    transcriber = Mock()
    transcriber.transcribe.return_value = TranscriptionResult("资料目录", "fake", "fake")
    events = []
    voice = VoiceService(settings=VoiceSettings(enabled=True), transcriber=transcriber, synthesizer=Mock(),
        conversation=ConversationService(None, task_router=router(task_store(tmp_path), factory)))
    run_voice_session(voice, recorder=Recorder(), max_turns=1, play=False, emit=events.append)
    run_id = first["result"]["task"]["run_id"]
    assert store.get(run_id)["user_answers"] == ["资料目录"]
    assert model.prompts[1]["user_answers"] == ["资料目录"]
    assert len(store.list()) == 1


def test_conflicting_new_task_selection_never_executes(tmp_path):
    pytest.importorskip("langgraph")
    store = task_store(tmp_path)
    other = seed(store)
    handler = Mock()
    def factory():
        session = store.task_session("default")
        store.update_task_session("default", session["revision"], run_id=other["run_id"], candidates=[])
        return PersistentExecutor(store, ExecutionRuntime(registry(handler, "allow"), Model(CALL)))
    result = router(store, factory).handle("start task: test")
    assert result["intent"] == "task_error"
    assert store.task_session("default")["run_id"] == other["run_id"]
    handler.assert_not_called()
    assert any(s["status"] == "created" for s in store.list())


def test_inflight_resume_does_not_retarget_changed_session(tmp_path):
    pytest.importorskip("langgraph")
    store = task_store(tmp_path)
    first, other = seed(store, "first"), seed(store, "other")
    def factory():
        session = store.task_session("default")
        store.update_task_session("default", session["revision"], run_id=other["run_id"], candidates=[])
        return PersistentExecutor(store, ExecutionRuntime(registry(lambda *args: {}), Model({"action": "ask_user", "question": "Which?"})))
    result = router(store, factory, run_id=first["run_id"]).handle("继续任务")
    assert result["result"]["task"]["run_id"] == first["run_id"]
    assert store.get(other["run_id"])["steps"] == 0


def test_missing_candidate_is_not_replaced_with_newest(tmp_path):
    store = task_store(tmp_path)
    a = seed(store)
    chat = router(store)
    chat.handle("任务列表")
    with store.connect() as db:
        db.execute("DELETE FROM runs WHERE id=?", (a["run_id"],))
    b = seed(store)
    assert chat.handle("选择任务 1")["intent"] == "task_error"
    assert store.task_session("default")["run_id"] is None


@pytest.mark.parametrize("arguments", [["--task-session", "x"], ["--task-mode", "--approve"],
                                      ["--task-mode", "--task-session", ""], ["--task-mode", "--task-session", "../escape"]])
def test_cli_rejects_invalid_task_options_before_initializing(tmp_path, monkeypatch, arguments):
    import sys
    from nexus import cli
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "_task_router", Mock(side_effect=AssertionError("Router must not initialize")))
    monkeypatch.setattr(sys, "argv", ["nexus", "ask", "查看进度", *arguments])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2


def test_cli_voice_task_status_does_not_construct_llm_or_embedding(tmp_path, monkeypatch, capsys):
    import sys
    from nexus import cli
    from nexus.config import VoiceSettings
    from test_voice import write_test_wav, FakeTranscriber, FakeSynthesizer
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    audio = write_test_wav(tmp_path / "input.wav")
    monkeypatch.setattr(cli, "load_voice_settings", lambda: VoiceSettings(enabled=True))
    monkeypatch.setattr(cli, "build_voice_providers", lambda settings: (None, FakeTranscriber("查看进度"), FakeSynthesizer()))
    monkeypatch.setattr(cli, "load_embedding_settings", Mock(side_effect=AssertionError("Embedding initialized")))
    monkeypatch.setattr(cli.LLMConfig, "from_env", Mock(side_effect=AssertionError("LLM initialized")))
    monkeypatch.setattr(sys, "argv", ["nexus", "voice", "ask", "--input", str(audio), "--task-mode", "--llm", "--no-play"])
    cli.main()
    result = json.loads(capsys.readouterr().out)
    assert result["conversation"]["intent"] == "task_select_required"


@pytest.mark.parametrize("status", ["cancelled", "failed", "reported_complete", "needs_review", "budget_exhausted"])
def test_stopped_states_never_restart(tmp_path, status):
    store = task_store(tmp_path)
    state = seed(store, status=status)
    assert router(store, run_id=state["run_id"]).handle("继续任务")["result"]["task"]["status"] == status
    assert len(store.list()) == 1


def test_selected_contextful_task_rechecks_sources(tmp_path):
    pytest.importorskip("langgraph")
    from test_execution_context import setup_context
    service, builder = setup_context(tmp_path)
    store = task_store(tmp_path)
    executor = PersistentExecutor(store, ExecutionRuntime(registry(lambda *args: {}),
        Model({"action": "ask_user", "question": "Which?"})), context_builder=builder)
    first = executor.start("research", context_options={})
    before = store.get(first["run_id"])
    service.store.mutate(lambda s: s["memories"][0].update(privacy="private"))
    result = router(store, lambda: executor, run_id=first["run_id"]).handle("answer: a folder")
    assert result["intent"] == "task_error"
    assert store.get(first["run_id"]) == before
