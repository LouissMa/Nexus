from __future__ import annotations

import json
import sys
import wave
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from nexus import cli
from nexus.config import (
    disable_voice_settings,
    load_voice_settings,
    update_profile_settings,
    update_voice_settings,
)
from nexus.voice import (
    SpeechResult,
    TranscriptionResult,
    VoiceConfigurationError,
    VoiceUnavailableError,
)


class FakeRecorder:
    def record(self, output_path: Path, *, seconds: int, sample_rate: int) -> Path:
        return write_test_wav(output_path, seconds=seconds, sample_rate=sample_rate)


class FakeTranscriber:
    def __init__(self, text: str = "show my goals") -> None:
        self.text = text

    def transcribe(
        self, audio_path: Path, *, language: str | None
    ) -> TranscriptionResult:
        return TranscriptionResult(
            text=self.text,
            provider="fake",
            model="test",
            language=language,
            duration_seconds=0.1,
        )


class FakeSynthesizer:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def synthesize(
        self,
        text: str,
        *,
        voice: str | None,
        output_path: Path | None,
        play: bool,
    ) -> SpeechResult:
        if self.fail:
            raise VoiceUnavailableError("speech is unavailable")
        return SpeechResult(
            provider="fake",
            played=play,
            output_path=str(output_path) if output_path is not None else None,
        )


class MisconfiguredSynthesizer:
    def synthesize(
        self,
        text: str,
        *,
        voice: str | None,
        output_path: Path | None,
        play: bool,
    ) -> SpeechResult:
        raise VoiceConfigurationError("configured voice is invalid")


@pytest.fixture
def isolated_nexus_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("NEXUS_HOME", str(home))
    for name in (
        "NEXUS_VOICE_ENABLED",
        "NEXUS_VOICE_TRANSCRIPTION_MODEL",
        "NEXUS_VOICE_LANGUAGE",
        "NEXUS_VOICE_SAMPLE_RATE",
        "NEXUS_VOICE_MAX_RECORD_SECONDS",
        "NEXUS_VOICE_MAX_AUDIO_BYTES",
        "NEXUS_VOICE_PLAY_AUDIO",
        "NEXUS_LLM_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    return home


def run_cli(arguments: list[str]) -> None:
    with patch.object(sys, "argv", ["nexus", *arguments]):
        cli.main()


def write_test_wav(
    path: Path, *, seconds: int = 1, sample_rate: int = 8_000
) -> Path:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00\x00" * seconds * sample_rate)
    return path


def fake_providers(
    text: str = "show my goals", *, speech_fails: bool = False
) -> tuple[FakeRecorder, FakeTranscriber, FakeSynthesizer]:
    return FakeRecorder(), FakeTranscriber(text), FakeSynthesizer(fail=speech_fails)


def configure_voice(home: Path, **overrides: object) -> None:
    values = {
        "enabled": True,
        "transcription_model": "base",
        "language": "auto",
        "play_audio": False,
    }
    values.update(overrides)
    update_voice_settings(path=home / "config.local.json", **values)


def test_voice_settings_default_to_disabled(tmp_path: Path) -> None:
    settings = load_voice_settings(env={}, path=tmp_path / "config.local.json")
    assert settings.enabled is False
    assert settings.transcription_provider == "faster_whisper"
    assert settings.transcription_model == "small"
    assert settings.synthesis_provider == "system"
    assert settings.max_record_seconds == 30
    assert settings.max_audio_bytes == 25 * 1024 * 1024


def test_voice_settings_persist_and_disable_transactionally(tmp_path: Path) -> None:
    path = tmp_path / "config.local.json"
    saved, returned_path = update_voice_settings(
        enabled=True,
        transcription_model="base",
        language="zh",
        voice="Microsoft Huihui Desktop",
        max_record_seconds=12,
        play_audio=False,
        path=path,
    )
    assert returned_path == path
    assert saved.enabled is True
    assert load_voice_settings(env={}, path=path).language == "zh"
    disabled, _ = disable_voice_settings(path=path)
    assert disabled.enabled is False
    assert disabled.transcription_model == "base"


def test_config_voice_set_show_and_disable_are_local_and_masked(
    isolated_nexus_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_cli(
        [
            "config", "voice", "set", "--enable", "--model", "base",
            "--language", "zh", "--voice", "Huihui", "--sample-rate", "16000",
            "--max-record-seconds", "12", "--max-audio-mib", "7", "--no-play",
        ]
    )
    saved = json.loads(capsys.readouterr().out)
    assert saved["voice"]["enabled"] is True
    assert saved["voice"]["transcription_model"] == "base"
    assert saved["voice"]["max_audio_bytes"] == 7 * 1024 * 1024

    run_cli(["config", "voice", "show"])
    shown = json.loads(capsys.readouterr().out)
    assert shown["voice"]["language"] == "zh"
    assert shown["voice"]["voice"] == "Huihui"

    run_cli(["config", "voice", "disable"])
    disabled = json.loads(capsys.readouterr().out)
    assert disabled["voice"]["enabled"] is False
    assert disabled["voice"]["transcription_model"] == "base"


def test_config_voice_partial_set_does_not_persist_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
    isolated_nexus_home: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_voice(isolated_nexus_home, transcription_model="base")
    monkeypatch.setenv("NEXUS_VOICE_TRANSCRIPTION_MODEL", "large-v3")

    run_cli(["config", "voice", "set", "--language", "zh"])
    capsys.readouterr()

    stored = load_voice_settings(
        env={}, path=isolated_nexus_home / "config.local.json"
    )
    assert stored.transcription_model == "base"
    assert stored.language == "zh"


def test_config_voice_json_normalizes_relative_config_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NEXUS_HOME", "relative-home")

    run_cli(["config", "voice", "set", "--enable"])

    result = json.loads(capsys.readouterr().out)
    assert result["path"] == str(
        (tmp_path / "relative-home" / "config.local.json").resolve()
    )


def test_voice_invalid_config_exits_two(
    isolated_nexus_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for arguments in (
        ["config", "voice", "set", "--sample-rate", "1"],
        ["config", "voice", "set", "--max-record-seconds", "0"],
    ):
        with pytest.raises(SystemExit) as raised:
            run_cli(arguments)
        assert raised.value.code == 2
        assert json.loads(capsys.readouterr().out)["status"] == "error"


def test_voice_ask_requires_exactly_one_audio_source() -> None:
    parser = cli.build_parser()
    with pytest.raises(SystemExit) as missing:
        parser.parse_args(["voice", "ask"])
    assert missing.value.code == 2
    with pytest.raises(SystemExit) as duplicate:
        parser.parse_args(
            ["voice", "ask", "--input", "input.wav", "--record-seconds", "2"]
        )
    assert duplicate.value.code == 2


def test_voice_ask_rejects_out_of_range_recording_as_invalid_argument(
    monkeypatch: pytest.MonkeyPatch,
    isolated_nexus_home: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_voice(isolated_nexus_home, max_record_seconds=5)
    monkeypatch.setattr(cli, "build_voice_providers", lambda settings: fake_providers())
    with pytest.raises(SystemExit) as raised:
        run_cli(["voice", "ask", "--record-seconds", "6", "--no-play"])
    assert raised.value.code == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"


def test_voice_status_is_disabled_without_loading_providers(
    monkeypatch: pytest.MonkeyPatch,
    isolated_nexus_home: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    availability = {
        "recording": {"provider": "sounddevice", "available": False},
        "transcription": {"provider": "faster_whisper", "available": False},
        "synthesis": {"provider": "system", "available": True},
    }
    monkeypatch.setattr(
        cli,
        "build_voice_providers",
        lambda settings: pytest.fail("status loaded voice providers"),
    )
    monkeypatch.setattr(
        cli,
        "voice_provider_availability",
        lambda settings: availability,
    )
    run_cli(["voice", "status"])
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "status": "ok",
        "voice": load_voice_settings().masked(),
        "providers": availability,
    }


def test_voice_record_transcribe_and_speak_return_structured_json(
    monkeypatch: pytest.MonkeyPatch,
    isolated_nexus_home: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_voice(isolated_nexus_home)
    monkeypatch.setattr(cli, "build_voice_providers", lambda settings: fake_providers())
    recording = tmp_path / "recording.wav"
    run_cli(["voice", "record", str(recording), "--seconds", "1"])
    recorded = json.loads(capsys.readouterr().out)
    assert recorded == {"status": "ok", "output_path": str(recording.resolve())}

    run_cli(["voice", "transcribe", str(recording)])
    transcribed = json.loads(capsys.readouterr().out)
    assert transcribed["transcript"]["text"] == "show my goals"

    speech_output = tmp_path / "speech.wav"
    run_cli(
        ["voice", "speak", "hello Nexus", "--output", str(speech_output), "--no-play"]
    )
    spoken = json.loads(capsys.readouterr().out)
    assert spoken["speech"]["output_path"] == str(speech_output.resolve())
    assert spoken["speech"]["played"] is False


def test_voice_provider_error_exits_one(
    monkeypatch: pytest.MonkeyPatch,
    isolated_nexus_home: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_voice(isolated_nexus_home)

    class UnavailableRecorder:
        def record(self, output_path: Path, *, seconds: int, sample_rate: int) -> Path:
            raise VoiceUnavailableError("optional recording dependency is missing")

    monkeypatch.setattr(
        cli,
        "build_voice_providers",
        lambda settings: (UnavailableRecorder(), FakeTranscriber(), FakeSynthesizer()),
    )
    with pytest.raises(SystemExit) as raised:
        run_cli(["voice", "record", str(tmp_path / "missing.wav"), "--seconds", "1"])
    assert raised.value.code == 1
    assert json.loads(capsys.readouterr().out) == {
        "status": "error",
        "error": "optional recording dependency is missing",
    }


def test_standalone_voice_configuration_error_exits_two(
    monkeypatch: pytest.MonkeyPatch,
    isolated_nexus_home: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_voice(isolated_nexus_home)
    monkeypatch.setattr(
        cli,
        "build_voice_providers",
        lambda settings: (
            FakeRecorder(),
            FakeTranscriber(),
            MisconfiguredSynthesizer(),
        ),
    )

    with pytest.raises(SystemExit) as raised:
        run_cli(["voice", "speak", "hello", "--no-play"])

    assert raised.value.code == 2
    assert json.loads(capsys.readouterr().out) == {
        "status": "error",
        "error": "configured voice is invalid",
    }


@pytest.mark.parametrize("command", ["ask", "briefing"])
def test_composed_voice_configuration_error_exits_two(
    command: str,
    monkeypatch: pytest.MonkeyPatch,
    isolated_nexus_home: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_voice(isolated_nexus_home)
    monkeypatch.setattr(
        cli,
        "build_voice_providers",
        lambda settings: (
            FakeRecorder(),
            FakeTranscriber(),
            MisconfiguredSynthesizer(),
        ),
    )
    arguments = ["voice", command, "--no-play"]
    if command == "ask":
        arguments.extend(["--input", str(write_test_wav(tmp_path / "input.wav"))])

    with pytest.raises(SystemExit) as raised:
        run_cli(arguments)

    assert raised.value.code == 2
    assert json.loads(capsys.readouterr().out) == {
        "status": "error",
        "error": "configured voice is invalid",
    }


def test_voice_ask_routes_transcript_through_unified_conversation(
    monkeypatch: pytest.MonkeyPatch,
    isolated_nexus_home: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_voice(isolated_nexus_home)
    audio = write_test_wav(tmp_path / "input.wav")
    monkeypatch.setattr(
        cli, "build_voice_providers", lambda settings: fake_providers("show my goals")
    )
    run_cli(["voice", "ask", "--input", str(audio), "--no-play"])
    result = json.loads(capsys.readouterr().out)
    assert result["transcript"]["text"] == "show my goals"
    assert result["conversation"]["intent"] == "list_goals"
    assert result["speech"]["played"] is False


def test_voice_ask_forwards_profile_approval_llm_intent_and_now(
    monkeypatch: pytest.MonkeyPatch,
    isolated_nexus_home: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_voice(isolated_nexus_home)
    update_profile_settings("Ada", "Asia/Shanghai")
    audio = write_test_wav(tmp_path / "input.wav")
    captured: dict[str, object] = {}
    fake_llm = object()

    class FakeLLMConfig:
        is_configured = True

    def fake_from_env(*, model_tier: str | None = None) -> FakeLLMConfig:
        captured["model_tier"] = model_tier
        return FakeLLMConfig()

    class CapturingConversation:
        def __init__(self, nexus: object, *, timezone: str, llm: object) -> None:
            captured["timezone"] = timezone
            captured["llm"] = llm

        def handle(self, text: str, **kwargs: object) -> dict[str, object]:
            captured["text"] = text
            captured.update(kwargs)
            return {"intent": "capture", "explanation": "captured", "result": {}}

    monkeypatch.setattr(cli.LLMConfig, "from_env", staticmethod(fake_from_env))
    monkeypatch.setattr(cli, "OpenAICompatibleLLM", lambda config: fake_llm)
    monkeypatch.setattr(cli, "ConversationService", CapturingConversation)
    monkeypatch.setattr(
        cli, "build_voice_providers", lambda settings: fake_providers("remember this")
    )
    run_cli(
        [
            "voice", "ask", "--input", str(audio), "--approve", "--llm",
            "--model-tier", "complex", "--show-intent", "--now",
            "2026-09-04T09:30:00+08:00", "--no-play",
        ]
    )
    json.loads(capsys.readouterr().out)
    assert captured["timezone"] == "Asia/Shanghai"
    assert captured["llm"] is fake_llm
    assert captured["model_tier"] == "complex"
    assert captured["approved"] is True
    assert captured["use_llm"] is True
    assert captured["show_intent"] is True
    assert captured["now"] == datetime.fromisoformat("2026-09-04T09:30:00+08:00")


def test_voice_briefing_uses_profile_and_preserves_text_on_tts_failure(
    monkeypatch: pytest.MonkeyPatch,
    isolated_nexus_home: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_voice(isolated_nexus_home)
    update_profile_settings("Ada", "Asia/Shanghai")
    monkeypatch.setattr(
        cli,
        "build_voice_providers",
        lambda settings: fake_providers(speech_fails=True),
    )
    run_cli(
        ["voice", "briefing", "--now", "2026-09-04T08:00:00+08:00", "--no-play"]
    )
    result = json.loads(capsys.readouterr().out)
    assert result["briefing"]["user_name"] == "Ada"
    assert "Ada" in result["speech_text"]
    assert result["speech"] is None
    assert result["degradations"] == ["speech_unavailable"]


def test_voice_briefing_forwards_llm_live_tools_and_agents(
    monkeypatch: pytest.MonkeyPatch,
    isolated_nexus_home: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_voice(isolated_nexus_home)
    update_profile_settings("Ada", "Asia/Shanghai")
    captured: dict[str, object] = {}

    class FakeLLMConfig:
        is_configured = True

    def fake_llm_config(*, model_tier: str | None = None) -> FakeLLMConfig:
        captured["llm_config_calls"] = int(captured.get("llm_config_calls", 0)) + 1
        captured["model_tier"] = model_tier
        return FakeLLMConfig()

    class FakeToolManager:
        def briefing_context(self, now: datetime | None) -> dict[str, object]:
            captured["tool_now"] = now
            return {"weather": {"summary": "sunny"}}

    class FakeOrchestrator:
        def __init__(self, service: object, **kwargs: object) -> None:
            pass

        def run_briefing(self, **kwargs: object) -> dict[str, object]:
            captured.update(kwargs)
            return {"briefing": "Agent briefing for Ada", "user_name": "Ada"}

    monkeypatch.setattr(
        cli.LLMConfig,
        "from_env",
        staticmethod(fake_llm_config),
    )
    monkeypatch.setattr(cli, "OpenAICompatibleLLM", lambda config: object())
    monkeypatch.setattr(
        cli, "build_tool_manager", lambda settings, home: FakeToolManager()
    )
    monkeypatch.setattr(cli, "build_mcp_manager", lambda settings, home: object())
    monkeypatch.setattr(cli, "AgentOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(cli, "build_voice_providers", lambda settings: fake_providers())
    run_cli(
        [
            "voice", "briefing", "--llm", "--model-tier", "complex",
            "--live-tools", "--agents", "--no-play",
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert result["briefing"]["briefing"] == "Agent briefing for Ada"
    assert captured["llm_config_calls"] == 1
    assert captured["model_tier"] == "complex"
    assert captured["user_name"] == "Ada"
    assert captured["use_llm"] is True
    assert captured["external_context"] == {"weather": {"summary": "sunny"}}
    assert getattr(captured["now"].tzinfo, "key", None) == "Asia/Shanghai"


def test_readmes_document_voice_setup_commands_and_listening_boundary() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    english = (repository_root / "README.md").read_text(encoding="utf-8")
    chinese = (repository_root / "README_zh.md").read_text(encoding="utf-8")
    commands = (
        'pip install -e ".[voice]"',
        "nexus config voice set --enable --model small --language auto",
        "nexus voice ask --record-seconds 5",
        "nexus voice briefing --live-tools",
    )

    for command in commands:
        assert command in english
        assert command in chinese
    assert "does not continuously listen" in english
    assert "不会持续监听" in chinese


def test_file_inventory_names_voice_modules() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    inventory = (repository_root / "docs" / "file_inventory.md").read_text(
        encoding="utf-8"
    )

    assert "`src/nexus/voice.py`" in inventory
    assert "`src/nexus/voice_providers.py`" in inventory


def test_architecture_documents_actual_voice_briefing_direction() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    architecture = (repository_root / "docs" / "architecture.md").read_text(
        encoding="utf-8"
    )

    assert "CLI _briefing_result -> existing briefing services" in architecture
    assert "-> VoiceService.narrate_briefing -> OS speech" in architecture
    assert (
        "The proactive scheduler separately consumes the same briefing services"
        in architecture
    )
    assert "briefing -> NexusService / Runtime" not in architecture


def test_architecture_lists_current_research_companion_limits() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    architecture = (repository_root / "docs" / "architecture.md").read_text(
        encoding="utf-8"
    )

    assert (
        "Research Companion still excludes OCR, JavaScript-rendered or "
        "authenticated crawling, arbitrary shell execution, container isolation, "
        "and unbounded background research."
    ) in architecture
    assert (
        "full-text ingestion, general web research, code execution, citation "
        "verification, and autonomous research loops remain future work"
        not in architecture
    )
