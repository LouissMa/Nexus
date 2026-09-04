from __future__ import annotations

import wave
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from nexus.config import VoiceSettings
from nexus.voice import (
    InvalidAudioError,
    SpeechResult,
    TranscriptionResult,
    VoiceConfigurationError,
    VoiceError,
    VoiceService,
    VoiceUnavailableError,
    render_briefing_speech,
    validate_audio_file,
)


NOW = datetime(2026, 9, 3, 8, 30, tzinfo=UTC)


def write_test_wav(
    path: Path,
    *,
    seconds: float = 0.1,
    sample_rate: int = 8_000,
) -> Path:
    frame_count = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\0\0" * frame_count)
    return path


def enabled_settings(**changes: Any) -> VoiceSettings:
    values = {
        "enabled": True,
        "max_audio_bytes": 1024 * 1024,
        "max_record_seconds": 2,
        **changes,
    }
    return VoiceSettings(**values)


def read_result() -> dict[str, Any]:
    return {
        "intent": "list_goals",
        "requires_approval": False,
        "preview": None,
        "result": {"goals": [{"title": "Ship Nexus"}]},
        "explanation": "Here are your goals.",
        "degradations": [],
    }


class FakeTranscriber:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[tuple[Path, str | None]] = []

    def transcribe(
        self, audio_path: Path, *, language: str | None
    ) -> TranscriptionResult:
        self.calls.append((audio_path, language))
        return TranscriptionResult(
            text=self.text,
            provider="fake-stt",
            model="tiny",
            language=language,
            duration_seconds=0.1,
        )


class FailingTranscriber:
    def transcribe(
        self, audio_path: Path, *, language: str | None
    ) -> TranscriptionResult:
        raise VoiceUnavailableError("transcription failed")


class FakeSynthesizer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None, Path | None, bool]] = []

    def synthesize(
        self,
        text: str,
        *,
        voice: str | None,
        output_path: Path | None,
        play: bool,
    ) -> SpeechResult:
        self.calls.append((text, voice, output_path, play))
        return SpeechResult(
            provider="fake-tts",
            played=play,
            output_path=str(output_path) if output_path else None,
        )


class FailingSynthesizer:
    def synthesize(
        self,
        text: str,
        *,
        voice: str | None,
        output_path: Path | None,
        play: bool,
    ) -> SpeechResult:
        raise VoiceUnavailableError("synthesis failed")


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


class UnexpectedSynthesizer:
    def synthesize(
        self,
        text: str,
        *,
        voice: str | None,
        output_path: Path | None,
        play: bool,
    ) -> SpeechResult:
        raise ValueError("programming error")


class FakeConversation:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def handle(self, text: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((text, kwargs))
        return self.result


class FakeRecorder:
    def __init__(self) -> None:
        self.path: Path | None = None
        self.calls: list[tuple[int, int]] = []

    def record(self, output_path: Path, *, seconds: int, sample_rate: int) -> Path:
        self.path = output_path
        self.calls.append((seconds, sample_rate))
        return write_test_wav(output_path, seconds=0.1, sample_rate=sample_rate)


def build_service(
    *,
    settings: VoiceSettings | None = None,
    recorder: Any = None,
    transcriber: Any = None,
    synthesizer: Any = None,
    conversation: Any = None,
) -> VoiceService:
    return VoiceService(
        settings=settings or enabled_settings(),
        recorder=recorder,
        transcriber=transcriber or FakeTranscriber("查看目标"),
        synthesizer=synthesizer or FakeSynthesizer(),
        conversation=conversation or FakeConversation(read_result()),
    )


def test_result_models_serialize_provider_metadata() -> None:
    transcript = TranscriptionResult(
        "hello", "local", "tiny", language="en", duration_seconds=1.25
    )
    speech = SpeechResult("system", True, "spoken.wav")

    assert transcript.to_dict() == {
        "text": "hello",
        "provider": "local",
        "model": "tiny",
        "language": "en",
        "duration_seconds": 1.25,
    }
    assert speech.to_dict() == {
        "provider": "system",
        "played": True,
        "output_path": "spoken.wav",
    }


def test_validate_audio_rejects_non_wav_and_oversized_files(tmp_path: Path) -> None:
    text = tmp_path / "input.txt"
    text.write_text("not audio", encoding="utf-8")
    with pytest.raises(InvalidAudioError, match="WAV"):
        validate_audio_file(text, max_bytes=1024)

    audio = write_test_wav(tmp_path / "large.wav")
    with pytest.raises(InvalidAudioError, match="size"):
        validate_audio_file(audio, max_bytes=16)


def test_validate_audio_rejects_missing_directory_and_invalid_header(
    tmp_path: Path,
) -> None:
    with pytest.raises(InvalidAudioError, match="regular file"):
        validate_audio_file(tmp_path / "missing.wav", max_bytes=1024)
    directory = tmp_path / "directory.wav"
    directory.mkdir()
    with pytest.raises(InvalidAudioError, match="regular file"):
        validate_audio_file(directory, max_bytes=1024)

    invalid = tmp_path / "invalid.wav"
    invalid.write_bytes(b"not a wav")
    with pytest.raises(InvalidAudioError, match="valid WAV"):
        validate_audio_file(invalid, max_bytes=1024)


def test_validate_audio_enforces_maximum_duration(tmp_path: Path) -> None:
    audio = write_test_wav(tmp_path / "long.wav", seconds=1.1)
    with pytest.raises(InvalidAudioError, match="duration"):
        validate_audio_file(audio, max_bytes=1024 * 1024, max_seconds=1)


def test_validate_audio_returns_resolved_regular_wav(tmp_path: Path) -> None:
    audio = write_test_wav(tmp_path / "valid.WAV")
    assert validate_audio_file(audio, max_bytes=1024 * 1024) == audio.resolve()


def test_voice_ask_rejects_disabled_settings_before_provider_calls(
    tmp_path: Path,
) -> None:
    audio = write_test_wav(tmp_path / "input.wav")
    transcriber = FakeTranscriber("查看目标")
    service = build_service(
        settings=VoiceSettings(enabled=False), transcriber=transcriber
    )

    with pytest.raises(VoiceConfigurationError, match="disabled"):
        service.ask(audio_path=audio)
    assert transcriber.calls == []


def test_voice_ask_preserves_conversation_approval_preview(tmp_path: Path) -> None:
    audio = write_test_wav(tmp_path / "input.wav")
    conversation = FakeConversation(
        {
            "intent": "add_goal",
            "requires_approval": True,
            "preview": {"intent": "add_goal"},
            "result": None,
            "explanation": "Review this local change.",
            "degradations": [],
        }
    )
    service = build_service(
        transcriber=FakeTranscriber("添加目标：复习 IELTS"),
        conversation=conversation,
    )

    result = service.ask(
        audio_path=audio,
        approved=False,
        use_llm=True,
        show_intent=True,
        now=NOW,
    )

    assert conversation.calls == [
        (
            "添加目标：复习 IELTS",
            {
                "approved": False,
                "use_llm": True,
                "show_intent": True,
                "now": NOW,
            },
        )
    ]
    assert result["conversation"]["preview"]["intent"] == "add_goal"
    assert "approval" in result["speech_text"].lower()


def test_failed_transcription_does_not_call_conversation(tmp_path: Path) -> None:
    audio = write_test_wav(tmp_path / "input.wav")
    conversation = FakeConversation(read_result())
    service = build_service(
        transcriber=FailingTranscriber(), conversation=conversation
    )

    with pytest.raises(VoiceUnavailableError, match="transcription failed"):
        service.ask(audio_path=audio)
    assert conversation.calls == []


def test_empty_transcript_does_not_call_conversation(tmp_path: Path) -> None:
    audio = write_test_wav(tmp_path / "input.wav")
    conversation = FakeConversation(read_result())
    service = build_service(
        transcriber=FakeTranscriber("  "), conversation=conversation
    )

    with pytest.raises(VoiceError, match="empty transcript"):
        service.ask(audio_path=audio)
    assert conversation.calls == []


def test_voice_ask_keeps_text_when_synthesis_fails(tmp_path: Path) -> None:
    audio = write_test_wav(tmp_path / "input.wav")
    service = build_service(synthesizer=FailingSynthesizer())

    result = service.ask(audio_path=audio)

    assert result["transcript"]["text"] == "查看目标"
    assert result["conversation"]["result"] is not None
    assert result["speech"] is None
    assert result["degradations"] == ["speech_unavailable"]


def test_voice_ask_propagates_synthesis_configuration_errors(tmp_path: Path) -> None:
    audio = write_test_wav(tmp_path / "input.wav")
    service = build_service(synthesizer=MisconfiguredSynthesizer())

    with pytest.raises(VoiceConfigurationError, match="configured voice is invalid"):
        service.ask(audio_path=audio)


def test_voice_ask_does_not_hide_non_voice_synthesis_errors(tmp_path: Path) -> None:
    audio = write_test_wav(tmp_path / "input.wav")
    service = build_service(synthesizer=UnexpectedSynthesizer())
    with pytest.raises(ValueError, match="programming error"):
        service.ask(audio_path=audio)


def test_voice_ask_records_to_owned_temporary_file_and_cleans_it() -> None:
    recorder = FakeRecorder()
    transcriber = FakeTranscriber("查看目标")
    service = build_service(recorder=recorder, transcriber=transcriber)

    result = service.ask(record_seconds=1)

    assert result["transcript"]["text"] == "查看目标"
    assert recorder.calls == [(1, 16_000)]
    assert recorder.path is not None
    assert transcriber.calls[0][0] == recorder.path.resolve()
    assert not recorder.path.exists()


def test_voice_ask_requires_recorder_only_when_recording(tmp_path: Path) -> None:
    service = build_service(recorder=None)
    audio = write_test_wav(tmp_path / "input.wav")

    assert service.ask(audio_path=audio)["transcript"]["text"] == "查看目标"
    with pytest.raises(VoiceUnavailableError, match="recorder"):
        service.ask(record_seconds=1)


def test_voice_ask_preserves_user_owned_input_after_failure(tmp_path: Path) -> None:
    audio = write_test_wav(tmp_path / "input.wav")
    service = build_service(transcriber=FailingTranscriber())

    with pytest.raises(VoiceUnavailableError):
        service.ask(audio_path=audio)
    assert audio.exists()


def test_voice_ask_rejects_ambiguous_or_excessive_recording_request() -> None:
    service = build_service(recorder=FakeRecorder())
    with pytest.raises(VoiceConfigurationError, match="exactly one"):
        service.ask()
    with pytest.raises(VoiceConfigurationError, match="exactly one"):
        service.ask(audio_path=Path("input.wav"), record_seconds=1)
    with pytest.raises(VoiceConfigurationError, match="between 1 and 2"):
        service.ask(record_seconds=3)


def test_briefing_renderer_and_narration_use_completed_mapping() -> None:
    briefing = {"briefing": "Good morning. Your first task is focused work."}
    synthesizer = FakeSynthesizer()
    service = build_service(synthesizer=synthesizer)

    result = service.narrate_briefing(briefing)

    assert render_briefing_speech(briefing) == briefing["briefing"]
    assert synthesizer.calls[0][0] == briefing["briefing"]
    assert result["briefing"] is briefing
    assert result["speech_text"] == briefing["briefing"]
    assert result["speech"]["provider"] == "fake-tts"
    assert result["degradations"] == []


def test_briefing_narration_preserves_text_when_synthesis_fails() -> None:
    briefing = {"briefing": "Good morning."}
    service = build_service(synthesizer=FailingSynthesizer())

    result = service.narrate_briefing(briefing)

    assert result == {
        "briefing": briefing,
        "speech_text": "Good morning.",
        "speech": None,
        "degradations": ["speech_unavailable"],
    }


def test_briefing_narration_propagates_synthesis_configuration_errors() -> None:
    service = build_service(synthesizer=MisconfiguredSynthesizer())

    with pytest.raises(VoiceConfigurationError, match="configured voice is invalid"):
        service.narrate_briefing({"briefing": "Good morning."})
