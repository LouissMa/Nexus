# Continuous Voice Sessions

The authorized Voice Assistant 2.0 increment adds explicit foreground, half-duplex
sessions to the existing voice stack. `nexus voice chat` owns the microphone only
while listening. WebRTC VAD uses 16 kHz mono PCM, 30 ms frames, a 300 ms pre-roll,
and a 900 ms end-of-speech pause. Recording retains the existing duration/byte
limits. The Whisper model is reused across turns.

The session emits flushed JSON-line listening, processing, turn, no_speech, and
session_end events. It defaults to 20 capture attempts and 30 seconds of idle
waiting per turn; bounds are 100 attempts and 120 seconds. Silence, exact English
or Chinese stop phrases, Ctrl+C, or a pending approval end the session. Temporary
audio is removed even on exceptions. No approvals carry across utterances.

The conversation router remains the existing command-oriented service. This
increment does not add chat-history grounding, pronoun resolution, wake words,
full-duplex audio, echo cancellation, speaker identification, or background
microphone access. `--llm` enables the existing optional LLM intent parser; audio
stays local, while transcribed text can enter that configured LLM path.

Validation covers real orchestration with fake audio/providers, microphone stream
release, VAD duration bounds, stop phrases, idle handling, approvals, interruption,
CLI composition, and existing voice regressions. Hardware audio quality requires
manual validation on the target device.
