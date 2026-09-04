from __future__ import annotations

import os
import platform
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any

from nexus.config import VoiceSettings
from nexus.voice import (
    AudioRecorder,
    SpeechSynthesizer,
    SpeechTranscriber,
    SpeechResult,
    TranscriptionResult,
    VoiceConfigurationError,
    VoiceError,
    VoiceUnavailableError,
)


_MAX_SPEECH_CHARACTERS = 4_000
_MAX_DIAGNOSTIC_CHARACTERS = 1_000
_WINDOWS_SPEECH_SCRIPT = r"""
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $text = [Console]::In.ReadToEnd()
    $voice = $args[0]
    $output = $args[1]
    $play = $args[2] -eq '1'
    if ($voice) { $synth.SelectVoice($voice) }
    if ($output) {
        $synth.SetOutputToWaveFile($output)
        $synth.Speak($text)
        $synth.SetOutputToDefaultAudioDevice()
    }
    if ($play) { $synth.Speak($text) }
}
finally {
    $synth.Dispose()
}
""".strip()


def _import_sounddevice() -> Any:
    import sounddevice

    return sounddevice


def _load_whisper_model(model_name: str) -> Any:
    from faster_whisper import WhisperModel

    return WhisperModel(model_name)


def _platform_name() -> str:
    return platform.system()


def _validated_output_path(output_path: Path, *, require_wav: bool = False) -> Path:
    path = Path(output_path).expanduser().resolve(strict=False)
    if not path.parent.is_dir():
        raise VoiceConfigurationError("The output parent must be an existing directory.")
    if path.exists() and not path.is_file():
        raise VoiceConfigurationError("The output path must refer to a regular file.")
    if require_wav and path.suffix.lower() != ".wav":
        raise VoiceConfigurationError("The recorder output path must use a WAV suffix.")
    return path


class SoundDeviceRecorder:
    def record(self, output_path: Path, *, seconds: int, sample_rate: int) -> Path:
        path = _validated_output_path(output_path, require_wav=True)
        if (
            isinstance(seconds, bool)
            or isinstance(sample_rate, bool)
            or seconds <= 0
            or sample_rate <= 0
        ):
            raise VoiceConfigurationError(
                "Recording seconds and sample rate must be positive integers."
            )
        try:
            sounddevice = _import_sounddevice()
        except ImportError as error:
            raise VoiceUnavailableError(
                "Audio recording requires the optional voice dependencies."
            ) from error

        frame_count = seconds * sample_rate
        recording = sounddevice.rec(
            frame_count,
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
        )
        sounddevice.wait()
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(sample_rate)
            audio.writeframes(recording.tobytes())
        return path


class FasterWhisperTranscriber:
    def __init__(self, model_name: str) -> None:
        if not isinstance(model_name, str) or not model_name.strip():
            raise VoiceConfigurationError("A Whisper model name is required.")
        self.model_name = model_name.strip()
        self._model: Any | None = None

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                self._model = _load_whisper_model(self.model_name)
            except ImportError as error:
                raise VoiceUnavailableError(
                    "Transcription requires the optional voice dependencies."
                ) from error
        return self._model

    def transcribe(
        self, audio_path: Path, *, language: str | None
    ) -> TranscriptionResult:
        path = Path(audio_path).expanduser().resolve(strict=False)
        if path.suffix.lower() != ".wav" or not path.is_file():
            raise VoiceConfigurationError(
                "Transcription input must be an existing WAV file."
            )
        segments, info = self._get_model().transcribe(
            str(path), language=language, vad_filter=True
        )
        text = " ".join(
            cleaned
            for segment in segments
            if (cleaned := str(segment.text).strip())
        )
        if not text:
            raise VoiceError("Transcription produced an empty transcript.")
        detected_language = getattr(info, "language", None) or language
        duration = getattr(info, "duration", None)
        return TranscriptionResult(
            text=text,
            provider="faster_whisper",
            model=self.model_name,
            language=detected_language,
            duration_seconds=duration,
        )


class SystemSpeechSynthesizer:
    def __init__(self, *, timeout_seconds: int = 30) -> None:
        if isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
            raise VoiceConfigurationError("Speech timeout must be a positive integer.")
        self.timeout_seconds = timeout_seconds

    def synthesize(
        self,
        text: str,
        *,
        voice: str | None,
        output_path: Path | None,
        play: bool,
    ) -> SpeechResult:
        if not isinstance(text, str) or not text.strip() or len(text) > _MAX_SPEECH_CHARACTERS:
            raise VoiceConfigurationError(
                "Speech text must contain between 1 and 4,000 characters."
            )
        if voice is not None and (not isinstance(voice, str) or not voice.strip()):
            raise VoiceConfigurationError("Speech voice must be a non-empty string.")
        path = (
            _validated_output_path(output_path)
            if output_path is not None
            else None
        )
        if not play and path is None:
            raise VoiceConfigurationError(
                "An output path is required when speech playback is disabled."
            )

        platform_name = _platform_name()
        executable = self._discover_executable(platform_name)
        commands = self._commands(
            platform_name,
            executable,
            voice=voice.strip() if voice else None,
            output_path=path,
            play=play,
        )
        for command in commands:
            self._run(command, text)
        return SpeechResult(
            provider="system",
            played=play,
            output_path=str(path) if path is not None else None,
        )

    def _discover_executable(self, platform_name: str) -> str:
        if platform_name == "Windows":
            executable = shutil.which("powershell.exe") or shutil.which("pwsh")
        elif platform_name == "Darwin":
            executable = "/usr/bin/say" if os.path.isfile("/usr/bin/say") else shutil.which("say")
        elif platform_name == "Linux":
            executable = shutil.which("espeak-ng") or shutil.which("espeak")
        else:
            raise VoiceUnavailableError(
                f"System speech is unavailable on operating system '{platform_name}'."
            )
        if executable is None:
            raise VoiceUnavailableError(
                f"No supported system speech executable was found for {platform_name}."
            )
        return executable

    def _commands(
        self,
        platform_name: str,
        executable: str,
        *,
        voice: str | None,
        output_path: Path | None,
        play: bool,
    ) -> list[list[str]]:
        if platform_name == "Windows":
            return [
                [
                    executable,
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    _WINDOWS_SPEECH_SCRIPT,
                    voice or "",
                    str(output_path) if output_path else "",
                    "1" if play else "0",
                ]
            ]

        base = [executable]
        if voice:
            base.extend(["-v", voice])
        output_command: list[str] | None = None
        if output_path is not None:
            output_flag = "-o" if platform_name == "Darwin" else "-w"
            output_command = [*base, output_flag, str(output_path)]
            if platform_name == "Linux":
                output_command.append("--stdin")
        play_command = [*base]
        if platform_name == "Linux":
            play_command.append("--stdin")
        commands = [output_command] if output_command is not None else []
        if play:
            commands.append(play_command)
        return [command for command in commands if command is not None]

    def _run(self, command: list[str], text: str) -> None:
        try:
            result = subprocess.run(
                command,
                shell=False,
                input=text,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise VoiceUnavailableError(
                f"System speech timed out after {self.timeout_seconds} seconds."
            ) from error
        except OSError as error:
            raise VoiceUnavailableError("System speech could not be started.") from error
        if result.returncode != 0:
            diagnostic = (result.stderr or "").strip()[:_MAX_DIAGNOSTIC_CHARACTERS]
            detail = f": {diagnostic}" if diagnostic else ""
            raise VoiceUnavailableError(
                f"System speech exited with code {result.returncode}{detail}"
            )


def build_voice_providers(
    settings: VoiceSettings,
) -> tuple[AudioRecorder, SpeechTranscriber, SpeechSynthesizer]:
    if settings.transcription_provider != "faster_whisper":
        raise VoiceConfigurationError(
            f"Unsupported transcription provider: {settings.transcription_provider}."
        )
    if settings.synthesis_provider != "system":
        raise VoiceConfigurationError(
            f"Unsupported synthesis provider: {settings.synthesis_provider}."
        )
    return (
        SoundDeviceRecorder(),
        FasterWhisperTranscriber(settings.transcription_model),
        SystemSpeechSynthesizer(),
    )
