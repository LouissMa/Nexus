import sys
import wave
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from nexus.voice import VoiceConfigurationError, VoiceService, TranscriptionResult
from nexus.config import VoiceSettings
from nexus.voice_session import SpeechTurnRecorder, run_voice_session


class Recorder:
    def __init__(self, available=True):
        self.available = available
        self.paths = []

    def record_turn(self, path, **kwargs):
        self.paths.append(path)
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b"\0\0" * 1600)
        return self.available


def service(text="show goals", approval=False):
    conversation = Mock()
    conversation.handle.return_value = {
        "explanation": "Goals", "requires_approval": approval, "result": None
    }
    transcriber = Mock()
    transcriber.transcribe.return_value = TranscriptionResult(text, "fake", "fake")
    return VoiceService(settings=VoiceSettings(enabled=True), transcriber=transcriber,
                        synthesizer=Mock(), conversation=conversation)


def test_session_repeats_and_cleans_audio():
    voice, recorder, events = service(), Recorder(), []
    result = run_voice_session(voice, recorder=recorder, max_turns=3, play=False, emit=events.append)
    assert result == {"event": "session_end", "reason": "turn_limit", "completed_turns": 3}
    assert voice.conversation.handle.call_count == 3
    assert all(call.kwargs["approved"] is False for call in voice.conversation.handle.call_args_list)
    assert all(not path.exists() for path in recorder.paths)
    voice.synthesizer.synthesize.assert_not_called()
    assert [e["event"] for e in events] == ["listening", "processing", "turn"] * 3 + ["session_end"]


@pytest.mark.parametrize("text", ["结束对话。", "STOP LISTENING!", "exit"])
def test_stop_phrase_never_dispatches(text):
    voice = service(text)
    result = run_voice_session(voice, recorder=Recorder(), play=False)
    assert result["reason"] == "stop_phrase"
    voice.conversation.handle.assert_not_called()


def test_stop_phrase_inside_request_is_not_stop():
    voice = service("search for stop listening techniques")
    assert run_voice_session(voice, recorder=Recorder(), max_turns=1, play=False)["completed_turns"] == 1


def test_silence_does_not_transcribe():
    voice = service()
    result = run_voice_session(voice, recorder=Recorder(False))
    assert result["reason"] == "idle_timeout"
    voice.transcriber.transcribe.assert_not_called()


def test_approval_stops_session_without_execution():
    voice = service(approval=True)
    assert run_voice_session(voice, recorder=Recorder(), play=False)["reason"] == "approval_required"
    assert voice.conversation.handle.call_count == 1
    assert voice.conversation.handle.call_args.kwargs["approved"] is False


def test_interrupt_cleans_up():
    voice, recorder = service(), Recorder()
    voice.transcriber.transcribe.side_effect = KeyboardInterrupt
    assert run_voice_session(voice, recorder=recorder)["reason"] == "interrupted"
    assert not recorder.paths[0].exists()


def test_empty_transcription_resumes_within_budget():
    voice, recorder, events = service(""), Recorder(), []
    result = run_voice_session(voice, recorder=recorder, max_turns=2, emit=events.append)
    assert result["completed_turns"] == 0
    assert sum(event["event"] == "no_speech" for event in events) == 2
    voice.conversation.handle.assert_not_called()
    assert all(not path.exists() for path in recorder.paths)


def test_provider_failure_cleans_recording_and_never_dispatches():
    from nexus.voice import VoiceUnavailableError

    voice, recorder = service(), Recorder()
    voice.transcriber.transcribe.side_effect = VoiceUnavailableError("Unavailable")
    with pytest.raises(VoiceUnavailableError):
        run_voice_session(voice, recorder=recorder)
    voice.conversation.handle.assert_not_called()
    assert not recorder.paths[0].exists()


def test_vad_ends_after_speech_pause(tmp_path, monkeypatch):
    stream = Mock()
    stream.__enter__ = Mock(return_value=stream)
    stream.__exit__ = Mock(return_value=False)
    stream.read.return_value = (b"\0\0" * 480, False)
    decisions = iter([False] * 5 + [True] * 10 + [False] * 30)
    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(RawInputStream=Mock(return_value=stream)))
    monkeypatch.setitem(sys.modules, "webrtcvad", SimpleNamespace(Vad=lambda mode: SimpleNamespace(is_speech=lambda data, rate: next(decisions))))
    assert SpeechTurnRecorder().record_turn(tmp_path / "turn.wav", max_seconds=30, idle_seconds=30)
    assert stream.read.call_count == 45
    stream.__exit__.assert_called_once()


@pytest.mark.parametrize("kwargs", [{"max_turns": 0}, {"max_turns": True}, {"idle_seconds": 121}])
def test_invalid_bounds(kwargs):
    with pytest.raises(VoiceConfigurationError):
        run_voice_session(service(), recorder=Recorder(), **kwargs)


@pytest.mark.parametrize("speech, expected", [(True, True), (False, False)])
def test_real_recorder_bounds_and_releases_stream(tmp_path, monkeypatch, speech, expected):
    stream = Mock()
    stream.__enter__ = Mock(return_value=stream)
    stream.__exit__ = Mock(return_value=False)
    stream.read.return_value = (b"\0\0" * 480, False)
    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(RawInputStream=Mock(return_value=stream)))
    monkeypatch.setitem(sys.modules, "webrtcvad", SimpleNamespace(Vad=lambda mode: SimpleNamespace(is_speech=lambda data, rate: speech)))
    path = tmp_path / "turn.wav"
    assert SpeechTurnRecorder().record_turn(path, max_seconds=1, idle_seconds=1) is expected
    stream.__exit__.assert_called_once()
    if expected:
        with wave.open(str(path)) as audio:
            assert 0 < audio.getnframes() / audio.getframerate() <= 1
    else:
        assert not path.exists()
