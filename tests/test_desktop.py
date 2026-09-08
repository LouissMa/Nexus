from pathlib import Path
from unittest.mock import Mock

import pytest

from nexus.conversation import ConversationService, IntentRegistry
from nexus.desktop import DesktopTaskService, find_local_files
from nexus.integrations.manager import build_tool_manager
from nexus.integrations.core import ToolError
from nexus.automation import AutomationManager, AutomationConfigurationError, AutomationPermissionError


def desktop(tmp_path, enabled=True):
    root = tmp_path / "pictures"
    root.mkdir(exist_ok=True)
    tools = build_tool_manager({"filesystem": {"enabled": enabled, "allowed_operations": ["search", "read"], "roots": [str(root)]}}, tmp_path)
    automations = Mock()
    automations.settings = {"chatgpt": {"type": "browser", "policy": "ask", "enabled": True}}
    automations.run.return_value = {"status": "success"}
    return DesktopTaskService(tools, automations, opener=Mock()), root


def test_search_names_images_and_session_selection(tmp_path):
    service, root = desktop(tmp_path)
    (root / "passport.jpg").write_bytes(b"image")
    (root / "other.txt").write_text("passport")
    result = service.search("护照照片")
    assert len(result["matches"]) == 1
    assert result["matches"][0]["name"] == "passport.jpg"
    assert service.candidate(1) == str(root / "passport.jpg")
    assert result["strategy"] == "filename"


def test_disabled_search_denied(tmp_path):
    service, _ = desktop(tmp_path, False)
    with pytest.raises(ToolError):
        service.search("passport")


def test_file_open_approval_roots_and_extensions(tmp_path):
    service, root = desktop(tmp_path)
    photo = root / "passport.jpg"
    photo.write_bytes(b"image")
    with pytest.raises(ToolError):
        service.open_file(str(photo), approved=False)
    assert service.open_file(str(photo), approved=True)["status"] == "launch_requested"
    service.opener.assert_called_once_with(str(photo))
    outside = tmp_path / "private.jpg"
    outside.write_bytes(b"image")
    with pytest.raises(ToolError):
        service.open_file(str(outside), approved=True)
    script = root / "script.exe"
    script.write_bytes(b"script")
    with pytest.raises(ToolError):
        service.open_file(str(script), approved=True)


@pytest.mark.parametrize("text, intent", [
    ("帮我找到我本地的护照照片", "find_files"),
    ("find files passport", "find_files"),
    ("打开文件 C:\\Pictures\\passport.jpg", "open_file"),
    ("打开第二张", "open_candidate"),
    ("Hi Nexus，帮我打开Chatgpt，我们开始今天的任务", "start_work"),
    ("打开ChatGPT", "open_application"),
    ("搜索研究 abc memory", "search_research_documents"),
])
def test_desktop_intents(text, intent):
    assert IntentRegistry().parse_local(text).name == intent


def test_desktop_routing_preserves_memory_punctuation():
    assert IntentRegistry().parse_local("remember Keep going!").arguments["text"] == "Keep going!"
    assert IntentRegistry().parse_local("打开chatgpt。").arguments["name"] == "chatgpt"


def test_conversation_search_open_preview_and_approved(tmp_path):
    service, root = desktop(tmp_path)
    (root / "passport.jpg").write_bytes(b"image")
    conversation = ConversationService(Mock(), desktop=service)
    assert len(conversation.handle("找到护照照片")["result"]["matches"]) == 1
    preview = conversation.handle("打开第一个")
    assert preview["requires_approval"]
    assert preview["preview"]["arguments"]["path"] == str(root / "passport.jpg")
    service.opener.assert_not_called()
    assert conversation.handle("打开第一个", approved=True)["result"]["status"] == "launch_requested"


def test_application_policy_and_workflow(tmp_path):
    service, _ = desktop(tmp_path)
    nexus = Mock()
    nexus.list_daily_tasks.return_value = [{"title": "Read paper"}]
    conversation = ConversationService(nexus, desktop=service)
    assert conversation.handle("打开chatgpt")["requires_approval"]
    service.automations.run.assert_not_called()
    service.automations.settings["chatgpt"]["policy"] = "allow"
    result = conversation.handle("打开chatgpt，我们开始今天的任务")
    assert result["result"]["tasks"] == [{"title": "Read paper"}]
    assert not result["requires_approval"]
    service.automations.settings["chatgpt"]["policy"] = "deny"
    assert conversation.handle("打开chatgpt", approved=True)["result"] is None


def test_unknown_application_and_missing_candidate_are_explained(tmp_path):
    service, _ = desktop(tmp_path)
    conversation = ConversationService(Mock(), desktop=service)
    for text in ("打开unknown", "打开第二张"):
        result = conversation.handle(text)
        assert result["result"] is None
        assert "desktop_action_failed" in result["degradations"]


def test_application_registered_path_and_permission(tmp_path, monkeypatch):
    from nexus import automation

    exe = tmp_path / "app.exe"
    exe.write_bytes(b"fake")
    manager = AutomationManager({"app": {"type": "application", "executable": str(exe), "policy": "ask"}}, tmp_path, Mock())
    with pytest.raises(AutomationPermissionError):
        manager.run("app")
    if automation.os.name == "nt":
        opener = Mock()
        monkeypatch.setattr(automation.os, "startfile", opener)
        result = manager.run("app", approved=True)
        assert result["launch_status"] == "launch_requested"
        opener.assert_called_once_with(str(exe))
    with pytest.raises(AutomationConfigurationError):
        AutomationManager({"bad": {"type": "application", "executable": "cmd.exe"}}, tmp_path, Mock())


def test_cli_search_uses_saved_permissions(tmp_path, monkeypatch, capsys):
    import json
    import sys
    from nexus import cli
    from nexus.config import update_tool_settings

    home = tmp_path / "home"
    root = tmp_path / "photos"
    root.mkdir()
    (root / "passport.png").write_bytes(b"image")
    monkeypatch.setenv("NEXUS_HOME", str(home))
    monkeypatch.delenv("NEXUS_FILESYSTEM_ROOTS", raising=False)
    update_tool_settings("filesystem", {"roots": [str(root)]})
    monkeypatch.setattr(sys, "argv", ["nexus", "ask", "帮我找到我本地的护照照片"])
    cli.main()
    result = json.loads(capsys.readouterr().out)
    assert result["result"]["matches"][0]["path"] == str(root / "passport.png")


def test_voice_routes_desktop_search(tmp_path):
    from nexus.config import VoiceSettings
    from nexus.voice import VoiceService, TranscriptionResult
    import wave

    desktop_service, root = desktop(tmp_path)
    (root / "passport.jpg").write_bytes(b"image")
    audio = tmp_path / "input.wav"
    with wave.open(str(audio), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 1600)
    transcriber = Mock()
    transcriber.transcribe.return_value = TranscriptionResult("找到护照照片", "fake", "fake")
    voice = VoiceService(settings=VoiceSettings(enabled=True), transcriber=transcriber,
                         synthesizer=Mock(), conversation=ConversationService(Mock(), desktop=desktop_service))
    result = voice.ask(audio_path=audio, session=True, play=False)
    assert len(result["conversation"]["result"]["matches"]) == 1


def test_unregistered_llm_application_is_never_launched(tmp_path):
    import json

    service, _ = desktop(tmp_path)
    llm = Mock()
    llm.generate.return_value = json.dumps({"intent": "open_application", "arguments": {"name": "unknown"}, "confidence": 0.99})
    result = ConversationService(Mock(), desktop=service, llm=llm).handle("please launch my favorite app", approved=True, use_llm=True)
    assert result["result"] is None
    service.automations.run.assert_not_called()
