from __future__ import annotations

import tempfile
import wave
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

from nexus.config import VoiceSettings


class VoiceError(RuntimeError):
    """Base error for voice operations."""


class VoiceConfigurationError(VoiceError):
    """Raised when voice configuration cannot support an operation."""


class VoiceUnavailableError(VoiceError):
    """Raised when a requested voice capability is unavailable."""


class InvalidAudioError(VoiceError):
    """Raised when an input audio file violates the local safety contract."""


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    provider: str
    model: str
    language: str | None = None
    duration_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SpeechResult:
    provider: str
    played: bool
    output_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@runtime_checkable
class AudioRecorder(Protocol):
    def record(self, output_path: Path, *, seconds: int, sample_rate: int) -> Path: ...


@runtime_checkable
class SpeechTranscriber(Protocol):
    def transcribe(
        self, audio_path: Path, *, language: str | None
    ) -> TranscriptionResult: ...


@runtime_checkable
class SpeechSynthesizer(Protocol):
    def synthesize(
        self,
        text: str,
        *,
        voice: str | None,
        output_path: Path | None,
        play: bool,
    ) -> SpeechResult: ...


def validate_audio_file(
    path: Path,
    *,
    max_bytes: int,
    max_seconds: float | None = None,
) -> Path:
    audio_path = Path(path).expanduser().resolve(strict=False)
    if audio_path.suffix.lower() != ".wav":
        raise InvalidAudioError("Audio input must be a WAV file.")
    if not audio_path.is_file():
        raise InvalidAudioError("Audio input must be an existing regular file.")
    try:
        size = audio_path.stat().st_size
    except OSError as error:
        raise InvalidAudioError("Audio input could not be inspected.") from error
    if max_bytes <= 0 or size > max_bytes:
        raise InvalidAudioError(
            f"Audio input size exceeds the configured {max_bytes}-byte limit."
        )

    try:
        with wave.open(str(audio_path), "rb") as audio:
            frame_rate = audio.getframerate()
            channels = audio.getnchannels()
            sample_width = audio.getsampwidth()
            frame_count = audio.getnframes()
    except (EOFError, OSError, wave.Error) as error:
        raise InvalidAudioError("Audio input is not a valid WAV file.") from error

    if min(frame_rate, channels, sample_width, frame_count) <= 0:
        raise InvalidAudioError("Audio input is not a valid WAV file.")
    duration_seconds = frame_count / frame_rate
    if max_seconds is not None and duration_seconds > max_seconds:
        raise InvalidAudioError(
            f"Audio input duration exceeds the configured {max_seconds}-second limit."
        )
    return audio_path


def render_conversation_speech(conversation: Mapping[str, Any]) -> str:
    explanation = conversation.get("explanation")
    explanation_text = explanation.strip() if isinstance(explanation, str) else ""
    if conversation.get("requires_approval") and conversation.get("result") is None:
        detail = explanation_text or "Review the requested change before it is applied."
        return f"Approval required. {detail}"
    if explanation_text:
        return explanation_text
    if conversation.get("result") is not None:
        return "Request completed."
    return "I could not complete that request."


def render_briefing_speech(briefing: Mapping[str, Any]) -> str:
    text = briefing.get("briefing")
    if not isinstance(text, str) or not text.strip():
        raise VoiceError("The completed briefing does not contain speech text.")
    return text.strip()


class VoiceService:
    def __init__(
        self,
        *,
        settings: VoiceSettings,
        transcriber: SpeechTranscriber,
        synthesizer: SpeechSynthesizer,
        conversation: Any,
        recorder: AudioRecorder | None = None,
    ) -> None:
        self.settings = settings
        self.recorder = recorder
        self.transcriber = transcriber
        self.synthesizer = synthesizer
        self.conversation = conversation

    def ask(
        self,
        *,
        audio_path: Path | None = None,
        record_seconds: int | None = None,
        approved: bool = False,
        use_llm: bool = False,
        show_intent: bool = False,
        now: datetime | None = None,
        output_path: Path | None = None,
        play: bool | None = None,
    ) -> dict[str, Any]:
        self._require_enabled()
        if (audio_path is None) == (record_seconds is None):
            raise VoiceConfigurationError(
                "Provide exactly one of audio_path or record_seconds."
            )

        owned_recording: Path | None = None
        try:
            if record_seconds is not None:
                if (
                    isinstance(record_seconds, bool)
                    or not 1 <= record_seconds <= self.settings.max_record_seconds
                ):
                    raise VoiceConfigurationError(
                        "record_seconds must be between 1 and "
                        f"{self.settings.max_record_seconds}."
                    )
                if self.recorder is None:
                    raise VoiceUnavailableError("An audio recorder is not available.")
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
                    owned_recording = Path(handle.name)
                recorded = self.recorder.record(
                    owned_recording,
                    seconds=record_seconds,
                    sample_rate=self.settings.sample_rate,
                )
                if Path(recorded).resolve(strict=False) != owned_recording.resolve(
                    strict=False
                ):
                    raise VoiceError("The recorder returned an unexpected output path.")
                selected_audio = owned_recording
            else:
                selected_audio = Path(audio_path)

            validated_audio = validate_audio_file(
                selected_audio,
                max_bytes=self.settings.max_audio_bytes,
                max_seconds=self.settings.max_record_seconds,
            )
            language = None if self.settings.language == "auto" else self.settings.language
            transcript = self.transcriber.transcribe(
                validated_audio,
                language=language,
            )
            if not transcript.text.strip():
                raise VoiceError("Transcription returned an empty transcript.")

            conversation = self.conversation.handle(
                transcript.text.strip(),
                approved=approved,
                use_llm=use_llm,
                show_intent=show_intent,
                now=now,
            )
            speech_text = render_conversation_speech(conversation)
            speech, synthesis_degradations = self._synthesize(
                speech_text,
                output_path=output_path,
                play=play,
            )
            degradations = list(conversation.get("degradations", []))
            degradations.extend(synthesis_degradations)
            return {
                "transcript": transcript.to_dict(),
                "conversation": conversation,
                "speech_text": speech_text,
                "speech": speech,
                "degradations": degradations,
            }
        finally:
            if owned_recording is not None:
                owned_recording.unlink(missing_ok=True)

    def narrate_briefing(
        self,
        briefing: Mapping[str, Any],
        *,
        output_path: Path | None = None,
        play: bool | None = None,
    ) -> dict[str, Any]:
        self._require_enabled()
        speech_text = render_briefing_speech(briefing)
        speech, degradations = self._synthesize(
            speech_text,
            output_path=output_path,
            play=play,
        )
        return {
            "briefing": briefing,
            "speech_text": speech_text,
            "speech": speech,
            "degradations": degradations,
        }

    def _require_enabled(self) -> None:
        if not self.settings.enabled:
            raise VoiceConfigurationError("Voice support is disabled.")

    def _synthesize(
        self,
        text: str,
        *,
        output_path: Path | None,
        play: bool | None,
    ) -> tuple[dict[str, Any] | None, list[str]]:
        should_play = self.settings.play_audio if play is None else play
        try:
            speech = self.synthesizer.synthesize(
                text,
                voice=self.settings.voice,
                output_path=output_path,
                play=should_play,
            )
        except VoiceUnavailableError:
            return None, ["speech_unavailable"]
        return speech.to_dict(), []
