# Voice Assistant MVP Final Fix Report

Date: 2026-09-05
Branch: `codex/voice-assistant-mvp`
Starting head: `53adde4626bbcbe13f0c79f8b11600c7c9542f90`

## Scope

This final wave resolves both Important review findings:

1. Windows system speech no longer places speech text, voice, output path, or
   playback state in the PowerShell argument tail. A fixed script reads one JSON
   payload from stdin; the argv ends at the fixed `-Command` script.
2. Operational failures from sounddevice recording/waiting/WAV writing and
   faster-whisper initialization/transcription/segment iteration are translated
   into static, bounded `VoiceUnavailableError` messages.

No Linux or macOS command construction changed. Existing `shell=False`, timeout,
captured diagnostics, and 1,000-character diagnostic truncation remain intact.

## Root Cause Evidence

- `SystemSpeechSynthesizer._commands` appended `voice`, `output_path`, and `play`
  after PowerShell's `-Command` script. Real Windows PowerShell treated the
  injection-like voice fixture as source and failed with a parser error.
- `SoundDeviceRecorder.record` called `sounddevice.rec`, `sounddevice.wait`, and
  `wave.open` without a provider-domain exception boundary.
- `FasterWhisperTranscriber` only normalized `ImportError` during model loading;
  initialization runtime errors and failures from `transcribe` or lazy segment
  iteration escaped unchanged.

## TDD Evidence

Environment for every pytest run:

```powershell
$env:PYTHONPATH='D:\AI_Projects\Nexus\.worktrees\voice-assistant-mvp\src'
$env:TEMP='D:\AI_Projects\Nexus\.worktrees\voice-assistant-mvp\.test-tmp'
$env:TMP=$env:TEMP
```

The initial sandboxed attempt could not create pytest capture files and did not
collect tests. The same focused command was rerun with write access for the real
RED observation.

### RED

Focused new regressions before production edits:

```text
10 failed in 1.75s
```

The failures directly exposed raw `RuntimeError`/`OSError`, the old dynamic
PowerShell argv entries, and the real PowerShell parser error caused by the
injection-like voice value.

### Focused GREEN

The identical focused selection after implementation:

```text
10 passed in 0.87s
```

This includes a real `powershell.exe` execution with a harmless script in place
of `System.Speech`. It round-trips an injection-like voice, speech text, a spaced
output path, and `play=false` through JSON stdin and verifies that no injection
sentinel is created.

### Complete Voice Suite

Command:

```text
pytest -q tests/test_voice.py tests/test_voice_providers.py tests/test_voice_cli.py
```

Result:

```text
70 passed in 2.02s
```

### Relevant CLI Regressions

Command:

```text
pytest -q tests/test_cli.py tests/test_conversation_cli.py tests/test_runtime_cli.py
```

Result:

```text
16 passed in 23.52s
```

### Fresh Full Suite

Command:

```text
pytest -q
```

Result:

```text
472 passed, 4 skipped in 132.77s (0:02:12)
```

Static check:

```text
ruff check --no-cache src/nexus/voice_providers.py tests/test_voice_providers.py tests/test_voice_cli.py
All checks passed!
```

`git diff --check` reported no whitespace errors. Git emitted only the existing
Windows line-ending conversion notices.

## Self-Review

- Windows argv contains only the discovered executable, fixed PowerShell flags,
  and the fixed script. JSON uses escaped ASCII by default, which avoids host
  code-page loss for non-ASCII speech and voice names.
- The PowerShell script converts JSON fields to explicit string/bool values and
  does not evaluate them. The real parser regression covers source-like content
  and a path containing spaces.
- Linux and macOS still receive raw speech text on stdin and retain their
  established argument-vector behavior.
- Recorder validation occurs before the operational guard, preserving
  `VoiceConfigurationError`. Missing optional dependencies retain their existing
  actionable error. Only device/capture/WAV operations are normalized.
- Whisper input/model-name validation remains `VoiceConfigurationError`, and a
  successful transcription with no text remains `VoiceError`. Initialization,
  transcribe, metadata access, and lazy segment iteration failures are normalized.
- Provider messages are fixed short strings, so raw driver, model-cache, device,
  and filesystem exception messages cannot reach CLI JSON. CLI tests also assert
  empty stderr and exit code 1.
- Exception chaining is retained for internal debugging while the CLI renders
  only the domain error message.
- No unrelated modules, configuration, documentation, or platform behavior were
  changed.

## Concerns

None identified. The real PowerShell regression is skipped on hosts without
PowerShell, but it executed and passed on this Windows review host; the platform-
independent argv/payload unit test remains active everywhere.
