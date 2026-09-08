from __future__ import annotations

import tempfile
import wave
from collections import deque
from pathlib import Path
from typing import Any, Callable

from nexus.voice import EmptyTranscriptionError, VoiceConfigurationError, VoiceService, VoiceUnavailableError


class SpeechTurnRecorder:
    """Capture one utterance with WebRTC VAD and bounded microphone ownership."""

    def record_turn(self, path: Path, *, max_seconds: int, idle_seconds: int) -> bool:
        try:
            import sounddevice
            import webrtcvad
        except ImportError as error:
            raise VoiceUnavailableError("Continuous voice requires the voice dependencies.") from error
        rate, frame_ms = 16000, 30
        frame_size = rate * frame_ms // 1000
        vad = webrtcvad.Vad(2)
        pre_roll: deque[bytes] = deque(maxlen=10)
        frames: list[bytes] = []
        silence = 0
        try:
            with sounddevice.RawInputStream(
                samplerate=rate, blocksize=frame_size, channels=1, dtype="int16"
            ) as stream:
                for _ in range((idle_seconds + max_seconds) * 1000 // frame_ms):
                    data, overflow = stream.read(frame_size)
                    if overflow:
                        raise VoiceUnavailableError("Microphone input overflowed; please retry.")
                    frame = bytes(data)
                    speaking = vad.is_speech(frame, rate)
                    if not frames:
                        pre_roll.append(frame)
                        if speaking:
                            frames.extend(pre_roll)
                        else:
                            silence += 1
                            if silence * frame_ms >= idle_seconds * 1000:
                                return False
                            continue
                    else:
                        frames.append(frame)
                    silence = 0 if speaking else silence + 1
                    if silence * frame_ms >= 900 or len(frames) >= max_seconds * 1000 // frame_ms:
                        break
            with wave.open(str(path), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(rate)
                audio.writeframes(b"".join(frames))
            return bool(frames)
        except VoiceUnavailableError:
            raise
        except Exception as error:
            raise VoiceUnavailableError("Continuous microphone recording failed.") from error


def run_voice_session(
    service: VoiceService,
    *,
    recorder: Any,
    max_turns: int = 20,
    idle_seconds: int = 30,
    use_llm: bool = False,
    play: bool = True,
    emit: Callable[[dict[str, Any]], None] = lambda event: None,
) -> dict[str, Any]:
    """Run sequential voice turns. Approval never carries across utterances."""
    service._require_enabled()
    for name, value, upper in (("max_turns", max_turns, 100), ("idle_seconds", idle_seconds, 120)):
        if type(value) is not int or not 1 <= value <= upper:
            raise VoiceConfigurationError(f"{name} must be between 1 and {upper}.")
    completed = 0
    reason = "turn_limit"
    try:
        for index in range(max_turns):
            emit({"event": "listening", "turn": index + 1})
            with tempfile.TemporaryDirectory(prefix="nexus-voice-") as directory:
                path = Path(directory) / "turn.wav"
                if not recorder.record_turn(
                    path, max_seconds=service.settings.max_record_seconds, idle_seconds=idle_seconds
                ):
                    reason = "idle_timeout"
                    break
                emit({"event": "processing", "turn": index + 1})
                try:
                    result = service.ask(audio_path=path, use_llm=use_llm, play=play, session=True)
                except EmptyTranscriptionError:
                    emit({"event": "no_speech", "turn": index + 1})
                    continue
            if result.get("session_stop"):
                reason = "stop_phrase"
                break
            completed += 1
            emit({"event": "turn", "turn": index + 1, **result})
            if result["conversation"].get("requires_approval"):
                reason = "approval_required"
                break
    except KeyboardInterrupt:
        reason = "interrupted"
    result = {"event": "session_end", "reason": reason, "completed_turns": completed}
    emit(result)
    return result
