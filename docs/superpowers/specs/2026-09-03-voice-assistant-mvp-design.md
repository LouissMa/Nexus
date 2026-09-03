# Voice Assistant MVP Design

Date: 2026-09-03
Status: Approved direction, pending implementation

## Objective

Add an explicit, local-first voice interface around the existing Nexus core. A user can record a short utterance, transcribe it, send the transcript through the same permissioned conversation entry point used by `nexus ask`, and hear a spoken response. Nexus can also narrate a generated morning briefing.

This phase adds an interface, not a second assistant brain. Conversation intent validation, mutation previews, approvals, planning, memory retrieval, tools, and LLM selection remain owned by their existing services.

## Scope

The MVP provides:

- Explicit push-to-talk recording with a user-selected maximum duration.
- Local speech-to-text through an optional Whisper-compatible provider.
- Local speech output through an operating-system speech provider.
- Standalone transcription and speech commands.
- A voice conversation command that routes transcripts through `ConversationService`.
- A briefing narration command that reuses `NexusService.daily_briefing`.
- Persistent, masked voice configuration and provider status diagnostics.
- Deterministic tests that use fake audio providers and require no microphone, speaker, model download, or API key.

The MVP does not provide continuous listening, wake-word activation, speaker identification, streaming duplex conversation, cloud audio upload, voice cloning, autonomous home control, or Dashboard microphone access.

## Approaches Considered

### 1. Local-only implementation

Bundle one recording, speech recognition, and speech synthesis stack. This is private and simple for users after installation, but it couples Nexus to heavy native dependencies and makes cross-platform failures difficult to isolate.

### 2. Hosted audio APIs only

Send recorded audio to a hosted transcription and speech API. This minimizes local setup, but requires a separate audio-capable provider, creates privacy and cost concerns, and would not work with text-only providers such as DeepSeek.

### 3. Pluggable local-first providers

Define narrow recorder, transcriber, and synthesizer interfaces. Ship optional local adapters and keep hosted adapters as a future extension. The orchestration layer does not depend on a specific audio library.

This is the selected approach. It preserves the existing local-first contract, keeps tests deterministic, and gives future wake-word, mobile, and robotics interfaces a stable boundary.

## Architecture

### Voice configuration

`VoiceSettings` is stored in the existing ignored local Nexus configuration. It records enabled state, transcription provider/model, synthesis provider/voice, language, recording limits, and playback preference. Display methods expose no secrets or sensitive paths beyond values the user explicitly configured.

Voice is disabled until explicitly configured. Text-only Nexus behavior is unchanged.

### Provider interfaces

Three focused protocols isolate optional dependencies:

- `AudioRecorder.record(...)` creates a bounded WAV file from an explicitly started recording.
- `SpeechTranscriber.transcribe(...)` returns a validated transcript and provider metadata.
- `SpeechSynthesizer.synthesize(...)` creates or plays bounded speech output.

The initial recorder uses `sounddevice` when the voice extra is installed. The initial transcriber uses `faster-whisper` with an explicitly configured model name or local model path. The initial synthesizer uses a bounded operating-system command with `shell=False`: Windows System.Speech, macOS `say`, or Linux `espeak`/`espeak-ng` when available.

Optional imports occur only when a provider is invoked. Missing dependencies and unsupported platforms produce actionable `VoiceUnavailableError` messages rather than breaking the rest of Nexus.

### Voice orchestration

`VoiceService` coordinates providers and existing Nexus services. It owns validation and temporary-file cleanup, but it does not parse intents or perform life-management mutations itself.

The voice conversation flow is:

1. The user explicitly starts recording or supplies an existing WAV file.
2. The transcriber returns text and non-sensitive metadata.
3. `ConversationService.handle` processes the text using the normal local-first intent registry and optional configured LLM intent parser.
4. If an action needs approval, the spoken and structured response explains that a preview is waiting; it does not apply the mutation.
5. A deterministic response renderer converts the result envelope to concise speech text.
6. The synthesizer creates speech output and optionally plays it.

The briefing flow calls the existing briefing service, renders its result for speech, and invokes the same synthesizer. It does not introduce a parallel briefing implementation.

## CLI Contract

Configuration:

```text
nexus config voice set [options]
nexus config voice show
nexus config voice disable
```

Voice operations:

```text
nexus voice status
nexus voice record OUTPUT.wav --seconds 5
nexus voice transcribe INPUT.wav
nexus voice speak "text" [--output OUTPUT.wav] [--no-play]
nexus voice ask [--input INPUT.wav | --record-seconds 5] [--approve] [--llm]
nexus voice briefing [--llm] [--live-tools] [--agents] [--no-play]
```

All commands return structured JSON consistent with the current CLI. `voice ask` includes transcript, conversation envelope, speech text, and speech metadata. Validation errors exit non-zero without leaking configuration secrets.

## Safety And Privacy

- Recording starts only from an explicit command and has a configured hard duration limit.
- There is no background microphone process and no wake-word listener in this phase.
- Audio stays local. The initial providers do not upload audio.
- Input files must be regular files with supported extensions and bounded size.
- Output parents must already exist; providers do not create arbitrary directory trees.
- External speech commands use fixed executable discovery, argument vectors, `shell=False`, timeouts, and capped diagnostic output.
- Voice does not bypass intent schemas, approval previews, tool policies, MCP policies, or automation policies.
- Temporary recordings are deleted after a voice request unless the user supplied an explicit output path.

## Failure Handling

Failures are separated into configuration, unavailable-provider, invalid-audio, transcription, synthesis, and conversation errors. A failed synthesis never rolls back a completed read-only conversation, and the JSON response still includes the transcript and conversation result. A failed transcription never calls the conversation layer.

For briefing narration, failure to speak returns the already generated briefing plus a speech degradation. Existing text output remains available.

## Files And Ownership

- `src/nexus/voice.py`: provider contracts, result models, validation, rendering, and orchestration.
- `src/nexus/voice_providers.py`: optional local recorder, Whisper transcriber, and operating-system TTS adapters.
- `src/nexus/config.py`: voice settings persistence and masked display.
- `src/nexus/cli.py`: voice and voice-configuration commands.
- `tests/test_voice.py`: orchestration, validation, cleanup, and degradation tests.
- `tests/test_voice_providers.py`: provider command/dependency boundary tests.
- `tests/test_voice_cli.py`: CLI contract and configuration tests.
- `README.md`, `README_zh.md`, roadmap, task checklist, architecture, and file inventory: user and maintainer documentation.

## Testing Strategy

Unit tests inject fake recorders, transcribers, synthesizers, and conversation services. They verify successful pipelines, approval preservation, limits, temporary-file cleanup, and partial speech failure.

Provider tests patch optional imports, executable discovery, and subprocess execution. No real microphone, speaker, network, or model is used in the default suite.

CLI tests use isolated Nexus homes and injected provider factories where needed. The final verification runs focused voice tests followed by the complete existing test suite.

## Acceptance Criteria

- Nexus works normally with no voice dependency installed and voice disabled.
- A configured local provider can transcribe a bounded WAV file.
- A transcript reaches the existing unified conversation path with approvals intact.
- A Nexus response and morning briefing can be rendered and spoken locally.
- Provider absence and speech failure degrade to useful structured text.
- Voice settings persist locally and are documented without exposing secrets.
- English and Chinese READMEs, architecture, roadmap, AIOS checklist, and file inventory describe the delivered feature and its limits.
- Focused and full automated test suites pass before the implementation is pushed.

