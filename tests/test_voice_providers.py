from __future__ import annotations

import json
import shutil
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from nexus.config import VoiceSettings
from nexus.voice import VoiceConfigurationError, VoiceError, VoiceUnavailableError
from nexus import voice_providers
from nexus.voice_providers import (
    FasterWhisperTranscriber,
    SoundDeviceRecorder,
    SystemSpeechSynthesizer,
    build_voice_providers,
)


def write_test_wav(path: Path, *, sample_rate: int = 8_000) -> Path:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\0\0" * 800)
    return path


class FakeRecording:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def tobytes(self) -> bytes:
        return self.data


class FakeSoundDevice:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int, int, str]] = []
        self.waited = False

    def rec(
        self, frames: int, *, samplerate: int, channels: int, dtype: str
    ) -> FakeRecording:
        self.calls.append((frames, samplerate, channels, dtype))
        return FakeRecording(b"\x01\x00" * frames)

    def wait(self) -> None:
        self.waited = True


class FailingSoundDevice(FakeSoundDevice):
    def __init__(self, stage: str, error: Exception) -> None:
        super().__init__()
        self.stage = stage
        self.error = error

    def rec(
        self, frames: int, *, samplerate: int, channels: int, dtype: str
    ) -> FakeRecording:
        if self.stage == "record":
            raise self.error
        return super().rec(
            frames, samplerate=samplerate, channels=channels, dtype=dtype
        )

    def wait(self) -> None:
        if self.stage == "wait":
            raise self.error
        super().wait()


class FakeSegment:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeWhisperModel:
    def __init__(self, segments: list[FakeSegment]) -> None:
        self.segments = segments
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def transcribe(self, path: str, **kwargs: Any) -> tuple[list[FakeSegment], Any]:
        self.calls.append((path, kwargs))
        return self.segments, SimpleNamespace(language="en", duration=0.1)


def completed(*, returncode: int = 0, stderr: str = "") -> Any:
    return subprocess.CompletedProcess([], returncode, stdout="", stderr=stderr)


def test_sounddevice_recorder_reports_missing_optional_dependency(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        voice_providers,
        "_import_sounddevice",
        lambda: (_ for _ in ()).throw(ImportError()),
    )

    with pytest.raises(VoiceUnavailableError, match="voice"):
        SoundDeviceRecorder().record(
            tmp_path / "recording.wav", seconds=1, sample_rate=16_000
        )


def test_sounddevice_recorder_writes_mono_pcm_int16_wav(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sounddevice = FakeSoundDevice()
    monkeypatch.setattr(voice_providers, "_import_sounddevice", lambda: sounddevice)

    output = SoundDeviceRecorder().record(
        tmp_path / "recording.wav", seconds=2, sample_rate=8_000
    )

    assert sounddevice.calls == [(16_000, 8_000, 1, "int16")]
    assert sounddevice.waited is True
    with wave.open(str(output), "rb") as audio:
        assert audio.getnchannels() == 1
        assert audio.getsampwidth() == 2
        assert audio.getframerate() == 8_000
        assert audio.getnframes() == 16_000


@pytest.mark.parametrize("stage", ["record", "wait"])
def test_sounddevice_recorder_normalizes_device_failures_without_leaking_details(
    stage: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secret = "device-secret-details"
    sounddevice = FailingSoundDevice(stage, RuntimeError(secret))
    monkeypatch.setattr(voice_providers, "_import_sounddevice", lambda: sounddevice)

    with pytest.raises(VoiceUnavailableError) as captured:
        SoundDeviceRecorder().record(
            tmp_path / "recording.wav", seconds=1, sample_rate=8_000
        )

    assert str(captured.value) == "Audio recording failed."
    assert secret not in str(captured.value)


def test_sounddevice_recorder_normalizes_wav_write_failures_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sounddevice = FakeSoundDevice()
    monkeypatch.setattr(voice_providers, "_import_sounddevice", lambda: sounddevice)
    monkeypatch.setattr(
        voice_providers.wave,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("private path")),
    )

    with pytest.raises(VoiceUnavailableError) as captured:
        SoundDeviceRecorder().record(
            tmp_path / "recording.wav", seconds=1, sample_rate=8_000
        )

    assert str(captured.value) == "Audio recording failed."
    assert "private path" not in str(captured.value)


def test_recorder_rejects_missing_output_parent(tmp_path: Path) -> None:
    with pytest.raises(VoiceConfigurationError, match="parent"):
        SoundDeviceRecorder().record(
            tmp_path / "missing" / "recording.wav", seconds=1, sample_rate=16_000
        )


def test_faster_whisper_joins_segments_without_loading_at_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model = FakeWhisperModel([FakeSegment("  hello "), FakeSegment(" world ")])
    loads: list[str] = []

    def load(model_name: str) -> FakeWhisperModel:
        loads.append(model_name)
        return model

    monkeypatch.setattr(voice_providers, "_load_whisper_model", load)
    transcriber = FasterWhisperTranscriber("small")
    input_path = write_test_wav(tmp_path / "input.wav")

    first = transcriber.transcribe(input_path, language=None)
    second = transcriber.transcribe(input_path, language="zh")

    assert first.text == "hello world"
    assert first.provider == "faster_whisper"
    assert first.model == "small"
    assert first.language == "en"
    assert loads == ["small"]
    assert model.calls == [
        (str(input_path.resolve()), {"language": None, "vad_filter": True}),
        (str(input_path.resolve()), {"language": "zh", "vad_filter": True}),
    ]
    assert second.text == "hello world"


def test_faster_whisper_reports_missing_optional_dependency(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        voice_providers,
        "_load_whisper_model",
        lambda _name: (_ for _ in ()).throw(ImportError()),
    )
    with pytest.raises(VoiceUnavailableError, match="voice"):
        FasterWhisperTranscriber("small").transcribe(
            write_test_wav(tmp_path / "input.wav"), language=None
        )


def test_faster_whisper_normalizes_model_initialization_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        voice_providers,
        "_load_whisper_model",
        lambda _name: (_ for _ in ()).throw(RuntimeError("private model cache")),
    )

    with pytest.raises(VoiceUnavailableError) as captured:
        FasterWhisperTranscriber("small").transcribe(
            write_test_wav(tmp_path / "input.wav"), language=None
        )

    assert str(captured.value) == "Speech transcription is unavailable."
    assert "private model cache" not in str(captured.value)


@pytest.mark.parametrize("failure_stage", ["transcribe", "iterate"])
def test_faster_whisper_normalizes_runtime_failures_without_leaking_details(
    failure_stage: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secret = "private device or model details"

    class FailingWhisperModel:
        def transcribe(self, *_args: Any, **_kwargs: Any) -> tuple[Any, Any]:
            if failure_stage == "transcribe":
                raise OSError(secret)

            def failing_segments() -> Any:
                raise RuntimeError(secret)
                yield

            return failing_segments(), SimpleNamespace(language="en", duration=0.1)

    monkeypatch.setattr(
        voice_providers, "_load_whisper_model", lambda _name: FailingWhisperModel()
    )

    with pytest.raises(VoiceUnavailableError) as captured:
        FasterWhisperTranscriber("small").transcribe(
            write_test_wav(tmp_path / "input.wav"), language=None
        )

    assert str(captured.value) == "Speech transcription failed."
    assert secret not in str(captured.value)


def test_faster_whisper_rejects_empty_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model = FakeWhisperModel([FakeSegment("  "), FakeSegment("")])
    monkeypatch.setattr(voice_providers, "_load_whisper_model", lambda _name: model)

    with pytest.raises(VoiceError, match="empty"):
        FasterWhisperTranscriber("small").transcribe(
            write_test_wav(tmp_path / "input.wav"), language=None
        )


def test_system_speech_uses_shell_false_stdin_and_bounded_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.setattr(voice_providers, "_platform_name", lambda: "Windows")
    monkeypatch.setattr(
        voice_providers.shutil,
        "which",
        lambda name: (
            "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
            if name == "powershell.exe"
            else None
        ),
    )
    monkeypatch.setattr(
        voice_providers.subprocess,
        "run",
        lambda args, **kwargs: calls.append((args, kwargs)) or completed(),
    )

    result = SystemSpeechSynthesizer(timeout_seconds=20).synthesize(
        "hello", voice=None, output_path=None, play=True
    )

    assert calls[0][0][0].endswith("powershell.exe")
    assert calls[0][0] == [
        "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        voice_providers._WINDOWS_SPEECH_SCRIPT,
    ]
    assert calls[0][1] == {
        "shell": False,
        "input": json.dumps(
            {"text": "hello", "voice": None, "output": None, "play": True}
        ),
        "text": True,
        "capture_output": True,
        "timeout": 20,
    }
    assert result.played is True


@pytest.mark.skipif(
    shutil.which("powershell.exe") is None and shutil.which("pwsh") is None,
    reason="PowerShell is required for the Windows parsing regression",
)
def test_windows_speech_payload_keeps_dynamic_values_out_of_powershell_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    assert powershell is not None
    sentinel = tmp_path / "injected.txt"
    output = tmp_path / "speech output with spaces.json"
    voice = f"voice'; Set-Content -LiteralPath '{sentinel}' owned; #"
    harmless_script = r"""
$payload = [Console]::In.ReadToEnd() | ConvertFrom-Json
[IO.File]::WriteAllText(
    [string]$payload.output,
    ($payload | ConvertTo-Json -Compress)
)
""".strip()
    monkeypatch.setattr(voice_providers, "_platform_name", lambda: "Windows")
    monkeypatch.setattr(voice_providers, "_system_speech_executable", lambda _name: powershell)
    monkeypatch.setattr(voice_providers, "_WINDOWS_SPEECH_SCRIPT", harmless_script)

    SystemSpeechSynthesizer().synthesize(
        "hello; Write-Output source", voice=voice, output_path=output, play=False
    )

    assert json.loads(output.read_text(encoding="utf-8-sig")) == {
        "text": "hello; Write-Output source",
        "voice": voice,
        "output": str(output.resolve()),
        "play": False,
    }
    assert not sentinel.exists()


@pytest.mark.parametrize("platform_name", ["Plan9", "FreeBSD"])
def test_system_speech_rejects_unsupported_operating_system(
    monkeypatch: pytest.MonkeyPatch, platform_name: str
) -> None:
    monkeypatch.setattr(voice_providers, "_platform_name", lambda: platform_name)
    with pytest.raises(VoiceUnavailableError, match="operating system"):
        SystemSpeechSynthesizer().synthesize(
            "hello", voice=None, output_path=None, play=True
        )


def test_system_speech_discovers_only_known_linux_executables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovered: list[str] = []
    calls: list[list[str]] = []
    monkeypatch.setattr(voice_providers, "_platform_name", lambda: "Linux")

    def which(name: str) -> str | None:
        discovered.append(name)
        return "/usr/bin/espeak" if name == "espeak" else None

    monkeypatch.setattr(voice_providers.shutil, "which", which)
    monkeypatch.setattr(
        voice_providers.subprocess,
        "run",
        lambda args, **_kwargs: calls.append(args) or completed(),
    )

    SystemSpeechSynthesizer().synthesize(
        "hello", voice="en-us", output_path=None, play=True
    )

    assert discovered == ["espeak-ng", "espeak"]
    assert calls == [["/usr/bin/espeak", "-v", "en-us", "--stdin"]]


def test_system_speech_no_play_writes_requested_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.setattr(voice_providers, "_platform_name", lambda: "Linux")
    monkeypatch.setattr(
        voice_providers.shutil,
        "which",
        lambda name: "/usr/bin/espeak-ng" if name == "espeak-ng" else None,
    )
    monkeypatch.setattr(
        voice_providers.subprocess,
        "run",
        lambda args, **kwargs: calls.append((args, kwargs)) or completed(),
    )
    output = tmp_path / "speech.wav"

    result = SystemSpeechSynthesizer().synthesize(
        "hello", voice="en", output_path=output, play=False
    )

    assert calls[0][0] == ["/usr/bin/espeak-ng", "-v", "en", "-w", str(output), "--stdin"]
    assert calls[0][1]["input"] == "hello"
    assert result.played is False
    assert result.output_path == str(output.resolve())


def test_system_speech_rejects_missing_output_parent(tmp_path: Path) -> None:
    with pytest.raises(VoiceConfigurationError, match="parent"):
        SystemSpeechSynthesizer().synthesize(
            "hello",
            voice=None,
            output_path=tmp_path / "missing" / "speech.wav",
            play=False,
        )


def test_system_speech_requires_output_when_playback_is_disabled() -> None:
    with pytest.raises(VoiceConfigurationError, match="output"):
        SystemSpeechSynthesizer().synthesize(
            "hello", voice=None, output_path=None, play=False
        )


def test_system_speech_caps_nonzero_exit_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(voice_providers, "_platform_name", lambda: "Linux")
    monkeypatch.setattr(voice_providers.shutil, "which", lambda _name: "/usr/bin/espeak-ng")
    monkeypatch.setattr(
        voice_providers.subprocess,
        "run",
        lambda _args, **_kwargs: completed(returncode=2, stderr="x" * 1_500),
    )

    with pytest.raises(VoiceUnavailableError) as captured:
        SystemSpeechSynthesizer().synthesize(
            "hello", voice=None, output_path=None, play=True
        )

    diagnostic = str(captured.value).split(": ", maxsplit=1)[1]
    assert diagnostic == "x" * 1_000


def test_system_speech_reports_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(voice_providers, "_platform_name", lambda: "Linux")
    monkeypatch.setattr(voice_providers.shutil, "which", lambda _name: "/usr/bin/espeak-ng")

    def timeout(*_args: Any, **_kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired("espeak-ng", 10)

    monkeypatch.setattr(voice_providers.subprocess, "run", timeout)
    with pytest.raises(VoiceUnavailableError, match="timed out"):
        SystemSpeechSynthesizer(timeout_seconds=10).synthesize(
            "hello", voice=None, output_path=None, play=True
        )


@pytest.mark.parametrize("text", ["", "   ", "x" * 4_001])
def test_system_speech_enforces_text_bounds(text: str) -> None:
    with pytest.raises(VoiceConfigurationError, match="text"):
        SystemSpeechSynthesizer().synthesize(
            text, voice=None, output_path=None, play=True
        )


def test_build_voice_providers_follows_voice_settings() -> None:
    settings = VoiceSettings(
        transcription_model="base",
        voice="Microsoft David Desktop",
    )

    recorder, transcriber, synthesizer = build_voice_providers(settings)

    assert isinstance(recorder, SoundDeviceRecorder)
    assert isinstance(transcriber, FasterWhisperTranscriber)
    assert transcriber.model_name == "base"
    assert isinstance(synthesizer, SystemSpeechSynthesizer)


def test_voice_provider_availability_uses_non_loading_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovered: list[str] = []

    def find_spec(name: str) -> object | None:
        discovered.append(name)
        return object() if name == "sounddevice" else None

    monkeypatch.setattr(voice_providers.importlib.util, "find_spec", find_spec)
    monkeypatch.setattr(
        voice_providers,
        "_system_speech_executable",
        lambda platform_name: "powershell.exe",
    )
    monkeypatch.setattr(
        voice_providers,
        "_load_whisper_model",
        lambda model_name: pytest.fail("availability loaded a Whisper model"),
    )

    result = voice_providers.voice_provider_availability(VoiceSettings())

    assert result == {
        "recording": {"provider": "sounddevice", "available": True},
        "transcription": {"provider": "faster_whisper", "available": False},
        "synthesis": {"provider": "system", "available": True},
    }
    assert discovered == ["sounddevice", "faster_whisper"]
