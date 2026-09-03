# Voice Assistant MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit, local-first voice interface that records or accepts WAV audio, transcribes it, routes it through Nexus's existing conversation and briefing services, and speaks the result without requiring an API key.

**Architecture:** Introduce narrow recorder, transcriber, and synthesizer protocols behind a `VoiceService`. Local optional adapters provide sounddevice capture, faster-whisper transcription, and bounded operating-system TTS; the CLI composes them with existing configuration, `ConversationService`, tool context, and briefing services.

**Tech Stack:** Python 3.11+, dataclasses/protocols, pathlib/wave/subprocess, optional `sounddevice` and `faster-whisper`, argparse, pytest.

**Spec:** `docs/superpowers/specs/2026-09-03-voice-assistant-mvp-design.md`

## Global Constraints

- Voice remains disabled until explicitly configured.
- Initial providers keep audio local and do not require an API key.
- Recording occurs only after an explicit command and is bounded to 1-120 seconds, with a configured default maximum of 30 seconds.
- Accepted input is a regular `.wav` file no larger than the configured maximum, defaulting to 25 MiB.
- Voice actions reuse existing conversation intent schemas, approval previews, LLM selection, tool policies, and briefing generation.
- Operating-system commands use fixed executable discovery, argument vectors, `shell=False`, bounded timeouts, and capped diagnostics.
- Default tests use fakes and never require a microphone, speaker, network, model download, or optional voice dependency.
- Continuous listening, wake words, speaker identity, streaming duplex audio, voice cloning, Dashboard microphone access, and home control remain out of scope.

## File Structure

- Create `src/nexus/voice.py`: errors, result models, provider protocols, validation, speech rendering, and `VoiceService` orchestration.
- Create `src/nexus/voice_providers.py`: optional sounddevice recorder, faster-whisper transcriber, and system TTS adapter.
- Modify `src/nexus/config.py`: immutable `VoiceSettings` plus transactional load/update/disable functions.
- Modify `src/nexus/cli.py`: `config voice` and `voice` command trees and composition helpers.
- Modify `pyproject.toml`: optional `voice` dependency group.
- Create `tests/test_voice.py`: core validation, orchestration, approval, cleanup, and degradation tests.
- Create `tests/test_voice_providers.py`: dependency and subprocess safety tests.
- Create `tests/test_voice_cli.py`: isolated configuration and end-to-end command contract tests.
- Modify `README.md`, `README_zh.md`, `docs/architecture.md`, `docs/roadmap.md`, `docs/aios_task_checklist.md`, and `docs/file_inventory.md`: feature, setup, safety, status, and ownership documentation.

---

### Task 1: Persistent Voice Configuration

**Files:**
- Modify: `src/nexus/config.py`
- Test: `tests/test_voice_cli.py`

**Interfaces:**
- Produces: `VoiceSettings`, `load_voice_settings(env=None, path=None)`, `update_voice_settings(..., path=None)`, and `disable_voice_settings(path=None)`.
- Stores: `config.local.json["voice"]` through the existing `mutate_local_config` transaction.

- [ ] **Step 1: Write failing configuration tests**

```python
from nexus.config import (
    disable_voice_settings,
    load_voice_settings,
    update_voice_settings,
)


def test_voice_settings_default_to_disabled(tmp_path):
    settings = load_voice_settings(env={}, path=tmp_path / "config.local.json")
    assert settings.enabled is False
    assert settings.transcription_provider == "faster_whisper"
    assert settings.transcription_model == "small"
    assert settings.synthesis_provider == "system"
    assert settings.max_record_seconds == 30
    assert settings.max_audio_bytes == 25 * 1024 * 1024


def test_voice_settings_persist_and_disable_transactionally(tmp_path):
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
```

- [ ] **Step 2: Run tests and confirm the missing interfaces fail**

Run: `pytest tests/test_voice_cli.py -q`

Expected: collection fails because the voice configuration interfaces do not exist.

- [ ] **Step 3: Implement immutable settings and validated persistence**

Add a frozen dataclass with these fields and defaults:

```python
@dataclass(frozen=True)
class VoiceSettings:
    enabled: bool = False
    transcription_provider: str = "faster_whisper"
    transcription_model: str = "small"
    synthesis_provider: str = "system"
    voice: str | None = None
    language: str = "auto"
    sample_rate: int = 16_000
    max_record_seconds: int = 30
    max_audio_bytes: int = 25 * 1024 * 1024
    play_audio: bool = True

    def masked(self) -> dict[str, Any]:
        return asdict(self)
```

`load_voice_settings` overlays `NEXUS_VOICE_*` environment values on stored values. `update_voice_settings` validates provider names (`faster_whisper`, `system`), language/model/voice string lengths, sample rate (8,000-48,000), recording seconds (1-120), and audio bytes (1 MiB-100 MiB). `disable_voice_settings` preserves all fields and changes only `enabled`.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_voice_cli.py -q`

Expected: configuration tests pass.

- [ ] **Step 5: Commit the configuration increment**

```bash
git add src/nexus/config.py tests/test_voice_cli.py
git commit -m "feat: add local voice configuration"
```

### Task 2: Voice Validation And Orchestration

**Files:**
- Create: `src/nexus/voice.py`
- Create: `tests/test_voice.py`

**Interfaces:**
- Consumes: `VoiceSettings` from Task 1 and any object exposing `handle(...)` or `daily_briefing(...)` through dependency injection.
- Produces: `VoiceError`, `VoiceConfigurationError`, `VoiceUnavailableError`, `InvalidAudioError`, `TranscriptionResult`, `SpeechResult`, `AudioRecorder`, `SpeechTranscriber`, `SpeechSynthesizer`, `validate_audio_file`, `render_conversation_speech`, `render_briefing_speech`, and `VoiceService`.

- [ ] **Step 1: Write failing validation and orchestration tests**

```python
def test_validate_audio_rejects_non_wav_and_oversized_files(tmp_path):
    text = tmp_path / "input.txt"
    text.write_text("not audio", encoding="utf-8")
    with pytest.raises(InvalidAudioError, match="WAV"):
        validate_audio_file(text, max_bytes=1024)


def test_voice_ask_preserves_conversation_approval_preview(tmp_path):
    audio = write_test_wav(tmp_path / "input.wav")
    conversation = FakeConversation(
        {"intent": "add_goal", "requires_approval": True, "preview": {"intent": "add_goal"}, "result": None, "explanation": "Review this local change.", "degradations": []}
    )
    service = VoiceService(
        settings=enabled_settings(),
        transcriber=FakeTranscriber("添加目标：复习 IELTS"),
        synthesizer=FakeSynthesizer(),
        conversation=conversation,
    )
    result = service.ask(audio_path=audio, approved=False)
    assert conversation.calls[0][1]["approved"] is False
    assert result["conversation"]["preview"]["intent"] == "add_goal"
    assert "approval" in result["speech_text"].lower()


def test_voice_ask_keeps_text_when_synthesis_fails(tmp_path):
    audio = write_test_wav(tmp_path / "input.wav")
    service = VoiceService(
        settings=enabled_settings(),
        transcriber=FakeTranscriber("查看目标"),
        synthesizer=FailingSynthesizer(),
        conversation=FakeConversation(read_result()),
    )
    result = service.ask(audio_path=audio)
    assert result["transcript"]["text"] == "查看目标"
    assert result["conversation"]["result"] is not None
    assert result["speech"] is None
    assert result["degradations"] == ["speech_unavailable"]
```

Also test empty transcripts, disabled settings, missing/non-regular input, invalid WAV headers, temporary recording cleanup, user-owned input preservation, maximum duration enforcement, and briefing rendering from `result["briefing"]`.

- [ ] **Step 2: Run core tests and confirm they fail**

Run: `pytest tests/test_voice.py -q`

Expected: collection fails because `nexus.voice` does not exist.

- [ ] **Step 3: Implement models, protocols, and validation**

Use frozen result dataclasses with `to_dict()` methods:

```python
@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    provider: str
    model: str
    language: str | None = None
    duration_seconds: float | None = None

@dataclass(frozen=True)
class SpeechResult:
    provider: str
    played: bool
    output_path: str | None = None
```

Define runtime-checkable protocols with these calls:

```python
class AudioRecorder(Protocol):
    def record(self, output_path: Path, *, seconds: int, sample_rate: int) -> Path: ...

class SpeechTranscriber(Protocol):
    def transcribe(self, audio_path: Path, *, language: str | None) -> TranscriptionResult: ...

class SpeechSynthesizer(Protocol):
    def synthesize(self, text: str, *, voice: str | None, output_path: Path | None, play: bool) -> SpeechResult: ...
```

`validate_audio_file` resolves a regular `.wav`, enforces size, and opens it with `wave.open` to verify a positive frame rate, channel count, sample width, and frame count.

- [ ] **Step 4: Implement renderers and `VoiceService`**

`VoiceService.ask` must:

1. Reject disabled configuration.
2. Use a supplied WAV or create a temporary WAV through the recorder.
3. Transcribe before calling conversation.
4. Call `conversation.handle(transcript, approved=..., use_llm=..., show_intent=..., now=...)`.
5. Render concise speech, preserving approval state.
6. Catch only voice synthesis errors and append `speech_unavailable`.
7. Delete only its own temporary recording in `finally`.

`VoiceService.narrate_briefing` receives or creates a briefing mapping, speaks `briefing["briefing"]`, and returns the briefing even when synthesis degrades.

- [ ] **Step 5: Run core tests**

Run: `pytest tests/test_voice.py -q`

Expected: all core voice tests pass.

- [ ] **Step 6: Commit the core increment**

```bash
git add src/nexus/voice.py tests/test_voice.py
git commit -m "feat: add voice orchestration core"
```

### Task 3: Optional Local Audio Providers

**Files:**
- Create: `src/nexus/voice_providers.py`
- Create: `tests/test_voice_providers.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: provider protocols, result models, and errors from `nexus.voice`; `VoiceSettings` from configuration.
- Produces: `SoundDeviceRecorder`, `FasterWhisperTranscriber`, `SystemSpeechSynthesizer`, and `build_voice_providers(settings)`.

- [ ] **Step 1: Write failing provider boundary tests**

```python
def test_sounddevice_recorder_reports_missing_optional_dependency(monkeypatch, tmp_path):
    monkeypatch.setattr(voice_providers, "_import_sounddevice", lambda: (_ for _ in ()).throw(ImportError()))
    with pytest.raises(VoiceUnavailableError, match="voice"):
        SoundDeviceRecorder().record(tmp_path / "recording.wav", seconds=1, sample_rate=16000)


def test_faster_whisper_joins_segments_without_loading_at_import(monkeypatch, tmp_path):
    model = FakeWhisperModel([FakeSegment("  hello "), FakeSegment(" world ")])
    monkeypatch.setattr(voice_providers, "_load_whisper_model", lambda *args: model)
    result = FasterWhisperTranscriber("small").transcribe(
        write_test_wav(tmp_path / "input.wav"), language=None
    )
    assert result.text == "hello world"
    assert result.provider == "faster_whisper"


def test_system_speech_uses_shell_false_and_bounded_timeout(monkeypatch):
    calls = []
    monkeypatch.setattr(voice_providers, "_platform_name", lambda: "Windows")
    monkeypatch.setattr(voice_providers.shutil, "which", lambda name: "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
    monkeypatch.setattr(voice_providers.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs)) or completed())
    SystemSpeechSynthesizer(timeout_seconds=20).synthesize("hello", voice=None, output_path=None, play=True)
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["timeout"] == 20
```

Also test recorder WAV format, duration/sample-rate arguments, empty Whisper output, provider construction, unsupported operating systems, non-zero process exits, output path handling, voice selection, and 4,000-character speech bounds.

- [ ] **Step 2: Run provider tests and confirm they fail**

Run: `pytest tests/test_voice_providers.py -q`

Expected: collection fails because the provider module does not exist.

- [ ] **Step 3: Implement lazy local recorder and transcriber adapters**

`SoundDeviceRecorder` lazily imports `sounddevice`, records mono `int16`, waits for completion, and writes a PCM WAV through `wave`. `FasterWhisperTranscriber` lazily imports `WhisperModel`, caches one model per adapter instance, transcribes with VAD filtering, joins non-empty segments, and rejects an empty transcript.

- [ ] **Step 4: Implement bounded system speech**

Discover only these executables:

- Windows: `powershell.exe` or `pwsh`, using a fixed System.Speech script and text on standard input.
- macOS: `/usr/bin/say` or discovered `say`.
- Linux: discovered `espeak-ng` or `espeak`.

Use `subprocess.run(..., shell=False, input=..., text=True, capture_output=True, timeout=...)`. Truncate stderr included in exceptions to 1,000 characters. Use direct playback when supported; otherwise create the requested WAV/AIFF and report `played=False` when `--no-play` is selected.

- [ ] **Step 5: Add the optional dependency group**

```toml
voice = [
  "sounddevice>=0.5,<1",
  "faster-whisper>=1.1,<2",
]
```

- [ ] **Step 6: Run provider and core tests**

Run: `pytest tests/test_voice.py tests/test_voice_providers.py -q`

Expected: all tests pass without installing the voice extra.

- [ ] **Step 7: Commit the provider increment**

```bash
git add src/nexus/voice_providers.py tests/test_voice_providers.py pyproject.toml
git commit -m "feat: add local voice providers"
```

### Task 4: CLI Composition And End-To-End Contract

**Files:**
- Modify: `src/nexus/cli.py`
- Modify: `tests/test_voice_cli.py`

**Interfaces:**
- Consumes: Task 1 configuration, Task 2 `VoiceService`, Task 3 `build_voice_providers`, existing `NexusService.converse`, `NexusService.daily_briefing`, agent orchestration, and tool manager.
- Produces: `nexus config voice set|show|disable` and `nexus voice status|record|transcribe|speak|ask|briefing`.

- [ ] **Step 1: Add failing parser and CLI tests**

```python
def test_config_voice_set_and_show_are_local_and_masked(isolated_nexus_home, capsys):
    run_cli(["config", "voice", "set", "--enable", "--model", "base", "--language", "zh", "--no-play"])
    saved = json.loads(capsys.readouterr().out)
    assert saved["voice"]["enabled"] is True
    assert saved["voice"]["transcription_model"] == "base"
    run_cli(["config", "voice", "show"])
    shown = json.loads(capsys.readouterr().out)
    assert shown["voice"]["language"] == "zh"


def test_voice_ask_routes_transcript_through_unified_conversation(monkeypatch, isolated_nexus_home, tmp_path, capsys):
    configure_voice(isolated_nexus_home)
    audio = write_test_wav(tmp_path / "input.wav")
    monkeypatch.setattr(cli, "build_voice_providers", lambda settings: fake_providers("查看目标"))
    run_cli(["voice", "ask", "--input", str(audio), "--no-play"])
    result = json.loads(capsys.readouterr().out)
    assert result["transcript"]["text"] == "查看目标"
    assert result["conversation"]["intent"] == "list_goals"
```

Also test mutually exclusive input/record options, approval forwarding, standalone record/transcribe/speak commands, disabled status, missing dependency error exit code, briefing text preservation on TTS failure, profile display name/time zone use, LLM tier forwarding, agent/live-tool forwarding, and JSON output paths.

- [ ] **Step 2: Run CLI tests and confirm parser failures**

Run: `pytest tests/test_voice_cli.py -q`

Expected: parser rejects unknown `voice` and `config voice` commands.

- [ ] **Step 3: Add parser trees with exact bounds**

`config voice set` accepts `--enable`, `--model`, `--language`, `--voice`, `--sample-rate`, `--max-record-seconds`, `--max-audio-mib`, and `--play/--no-play`. `voice ask` uses a required mutually exclusive group for `--input` and `--record-seconds`; all commands support `--output`/`--no-play` only where meaningful.

- [ ] **Step 4: Add a composition helper and command dispatch**

Build settings and providers only inside the voice branch so ordinary CLI startup does not import optional audio packages. Compose `ConversationService(service, timezone=profile.timezone, llm=service.llm)` for `voice ask`. Reuse the existing briefing branch's LLM, live tool, and agent behavior for `voice briefing`; do not duplicate briefing generation rules.

Catch `VoiceError` at the command boundary, print `{"status": "error", "error": ...}`, and exit with code 1. Invalid CLI/config values exit with code 2.

- [ ] **Step 5: Run all voice tests**

Run: `pytest tests/test_voice.py tests/test_voice_providers.py tests/test_voice_cli.py -q`

Expected: all voice tests pass.

- [ ] **Step 6: Run neighboring regression tests**

Run: `pytest tests/test_cli.py tests/test_conversation.py tests/test_conversation_cli.py tests/test_scheduler.py -q`

Expected: all neighboring tests pass.

- [ ] **Step 7: Commit the CLI increment**

```bash
git add src/nexus/cli.py tests/test_voice_cli.py
git commit -m "feat: expose local voice assistant CLI"
```

### Task 5: User And Architecture Documentation

**Files:**
- Modify: `README.md`
- Modify: `README_zh.md`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/aios_task_checklist.md`
- Modify: `docs/file_inventory.md`

**Interfaces:**
- Documents: exact installation, setup, commands, local/API behavior, privacy boundaries, module ownership, current capabilities, and remaining Phase 13 work.

- [ ] **Step 1: Add documentation assertions before editing prose**

Extend a lightweight existing documentation test or `tests/test_voice_cli.py` to assert that both READMEs contain `pip install -e ".[voice]"`, `nexus config voice set`, `nexus voice ask`, `nexus voice briefing`, and an explicit no-continuous-listening statement. Assert the file inventory names both new source modules.

- [ ] **Step 2: Run the documentation assertions and confirm failure**

Run: `pytest tests/test_voice_cli.py -q`

Expected: documentation assertions fail because voice usage is absent.

- [ ] **Step 3: Update English and Chinese user documentation**

Document:

```text
pip install -e ".[voice]"
nexus config voice set --enable --model small --language auto
nexus voice ask --record-seconds 5
nexus voice briefing --live-tools
```

Explain that text features require no voice dependency, DeepSeek remains usable for text generation but does not provide the local STT/TTS path, faster-whisper may download its configured model on first use, OS speech availability varies, and audio is not uploaded by the initial adapters.

- [ ] **Step 4: Update maintainer documents**

Mark only the Voice Assistant MVP subset complete in Phase 13. Leave wake word, visual context, family profiles, smart home, and robotics unchecked. Add both new modules and three tests to the inventory, and show the voice layer beside conversation/runtime in the architecture data flow.

- [ ] **Step 5: Run documentation and voice tests**

Run: `pytest tests/test_voice_cli.py tests/test_voice.py tests/test_voice_providers.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit documentation**

```bash
git add README.md README_zh.md docs/architecture.md docs/roadmap.md docs/aios_task_checklist.md docs/file_inventory.md tests/test_voice_cli.py
git commit -m "docs: document voice assistant MVP"
```

### Task 6: Verification And Release

**Files:**
- Modify only files required by verified failures.

**Interfaces:**
- Produces: a clean, pushed `main` implementation with evidence from focused tests, full tests, CLI smoke checks, and repository status.

- [ ] **Step 1: Run static repository checks**

Run: `git diff --check`

Expected: no whitespace errors.

- [ ] **Step 2: Run focused voice tests with a fresh temporary base**

Run: `pytest tests/test_voice.py tests/test_voice_providers.py tests/test_voice_cli.py -q --basetemp=.test-tmp-voice-focused`

Expected: all voice tests pass.

- [ ] **Step 3: Run the complete suite**

Run: `pytest -q --basetemp=.test-tmp-voice-full`

Expected: all tests pass, with only documented optional-dependency skips.

- [ ] **Step 4: Run CLI smoke checks without optional dependencies**

Run: `nexus config voice show`

Expected: valid JSON with masked/non-secret settings.

Run: `nexus voice status`

Expected: valid JSON reporting enabled/configured state and provider availability without importing or downloading a model.

- [ ] **Step 5: Review tracked changes and protect unrelated artifacts**

Run: `git status --short`

Expected: only intended tracked changes plus the pre-existing untracked `.manual`, `.playwright-cli`, demo, output, and inaccessible `.test-tmp-*` artifacts. Do not stage or delete those artifacts.

- [ ] **Step 6: Resolve any verification failure in its owning task**

If a check fails, return to the task that owns the failing file, add a regression test that reproduces the failure, implement the smallest correction, rerun that task's focused tests, and repeat Steps 1-5. When every check passes, proceed without a verification-only commit.

- [ ] **Step 7: Push the completed phase**

Run: `git push origin main`

Expected: `origin/main` advances to the final verified local commit.

- [ ] **Step 8: Confirm remote parity**

Run: `git status --short --branch`

Expected: `main` is aligned with `origin/main`; only known untracked artifacts remain.
