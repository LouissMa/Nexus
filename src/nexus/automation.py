from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import signal
import threading
import uuid
import webbrowser
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic, sleep
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit

from .config import local_config_path
from .runtime_config import RUNTIME_JOB_NAMES
from .store import JsonStore


AUTOMATION_TYPES = {"browser", "command", "github_inspect", "status_report"}
AUTOMATION_POLICIES = {"deny", "ask", "allow"}
ACTION_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
SAFE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$")
MAX_COMMAND_OUTPUT_BYTES = 1_000_000
MAX_GITHUB_LIMIT = 100
MAX_AUDIT_EVENTS = 1_000

_COMMON_FIELDS = {"type", "enabled", "policy"}
_TYPE_FIELDS = {
    "browser": _COMMON_FIELDS | {"url", "allowed_hosts"},
    "command": _COMMON_FIELDS
    | {"argv", "cwd", "allowed_roots", "timeout_seconds", "max_output_bytes"},
    "github_inspect": _COMMON_FIELDS | {"repo", "limit"},
    "status_report": _COMMON_FIELDS | {"output_path", "allowed_roots"},
}
_MASKED_FIELDS = {"url", "allowed_hosts", "argv", "cwd", "allowed_roots", "output_path"}
_TASK_STATUSES = ("pending", "in_progress", "completed", "blocked")


class AutomationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.audit_warning: str | None = None


class AutomationConfigurationError(AutomationError):
    def __init__(self, message: str):
        super().__init__("automation_configuration_invalid", message)


class AutomationPermissionError(AutomationError):
    pass


class AutomationExecutionError(AutomationError):
    pass


def load_automation_settings(
    path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    config_path = _automation_config_path(path)
    with _interprocess_path_lock(config_path):
        config = _read_automation_config(config_path)
        return _validate_automation_map(config.get("automations", {}))


def upsert_automation(
    name: str,
    definition: dict[str, Any],
    *,
    path: Path | None = None,
) -> tuple[dict[str, dict[str, Any]], Path]:
    _validate_definition(name, definition)
    config_path = _automation_config_path(path)
    with _interprocess_path_lock(config_path):
        config = _read_automation_config(config_path)
        stored = config.get("automations", {})
        if not isinstance(stored, dict):
            raise AutomationConfigurationError(
                "Automation configuration must be an object."
            )
        prospective = dict(stored)
        prospective[name] = definition
        validated = _validate_automation_map(prospective)
        config["automations"] = validated
        _atomic_write_json(config_path, config)
        return deepcopy(validated), config_path


def remove_automation(
    name: str,
    *,
    path: Path | None = None,
) -> tuple[dict[str, dict[str, Any]], Path]:
    _validate_action_name(name)
    config_path = _automation_config_path(path)
    with _interprocess_path_lock(config_path):
        config = _read_automation_config(config_path)
        stored = config.get("automations", {})
        if not isinstance(stored, dict):
            raise AutomationConfigurationError(
                "Automation configuration must be an object."
            )
        if name not in stored:
            raise AutomationConfigurationError(f"Unknown automation '{name}'.")
        prospective = dict(stored)
        del prospective[name]
        validated = _validate_automation_map(prospective)
        config["automations"] = validated
        _atomic_write_json(config_path, config)
        return deepcopy(validated), config_path


def masked_automation_settings(
    settings: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    masked = _deep_thaw(settings)
    for definition in masked.values():
        for field in _MASKED_FIELDS:
            if field in definition and definition[field] not in (None, [], (), ""):
                definition[field] = "***configured***"
    return masked


_PATH_LOCKS: dict[str, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()
_LOCK_TIMEOUT_SECONDS = 10.0
_LOCK_RETRY_SECONDS = 0.025


def _canonical_path(path: Path) -> Path:
    return Path(path).resolve(strict=False)


def _shared_path_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(str(_canonical_path(path)))
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


def _automation_config_path(path: Path | None) -> Path:
    return _canonical_path(Path(path) if path is not None else local_config_path())


def _try_os_lock(handle: Any) -> bool:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _release_os_lock(handle: Any) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _interprocess_path_lock(
    path: Path,
    *,
    timeout_seconds: float = _LOCK_TIMEOUT_SECONDS,
) -> Any:
    canonical = _canonical_path(path)
    process_lock = _shared_path_lock(canonical)
    deadline = monotonic() + max(0.1, timeout_seconds)
    if not process_lock.acquire(timeout=max(0.1, timeout_seconds)):
        raise AutomationConfigurationError("Timed out acquiring automation lock.")
    handle = None
    acquired = False
    try:
        canonical.parent.mkdir(parents=True, exist_ok=True)
        lock_path = canonical.with_name(f".{canonical.name}.lock")
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        handle = os.fdopen(descriptor, "r+b", buffering=0)
        if os.name == "nt" and lock_path.stat().st_size == 0:
            handle.write(b"\0")
            handle.flush()
        while not acquired:
            acquired = _try_os_lock(handle)
            if acquired:
                break
            if monotonic() >= deadline:
                raise AutomationConfigurationError(
                    "Timed out acquiring automation lock."
                )
            sleep(_LOCK_RETRY_SECONDS)
        yield canonical
    except AutomationConfigurationError:
        raise
    except OSError as exc:
        raise AutomationConfigurationError(
            "Unable to acquire automation lock."
        ) from exc
    finally:
        if handle is not None:
            try:
                if acquired:
                    _release_os_lock(handle)
            finally:
                handle.close()
        process_lock.release()


def _read_automation_config(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise AutomationConfigurationError(
            "Unable to load automation configuration."
        ) from exc
    try:
        config = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AutomationConfigurationError(
            "Unable to load automation configuration."
        ) from exc
    if not isinstance(config, dict):
        raise AutomationConfigurationError("Local configuration must be an object.")
    return config


def _validate_automation_map(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise AutomationConfigurationError(
            "Automation configuration must be an object."
        )
    return {
        name: _validate_definition(name, definition)
        for name, definition in value.items()
    }


def _windows_replace_file(source: Path, destination: Path) -> None:
    import ctypes
    from ctypes import wintypes

    replace_file = ctypes.WinDLL("kernel32", use_last_error=True).ReplaceFileW
    replace_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPVOID,
    ]
    replace_file.restype = wintypes.BOOL
    if not replace_file(
        str(destination),
        str(source),
        None,
        0x00000001,
        None,
        None,
    ):
        raise ctypes.WinError(ctypes.get_last_error())


def _replace_preserving_metadata(
    source: Path,
    destination: Path,
    *,
    platform_name: str | None = None,
    windows_replacer: Callable[[Path, Path], None] | None = None,
) -> None:
    platform = os.name if platform_name is None else platform_name
    try:
        if platform == "nt":
            if destination.exists():
                (windows_replacer or _windows_replace_file)(source, destination)
            else:
                os.replace(source, destination)
            return

        if destination.exists():
            metadata = destination.stat()
            os.chmod(source, metadata.st_mode & 0o7777)
            if (
                hasattr(os, "chown")
                and hasattr(os, "geteuid")
                and metadata.st_uid == os.geteuid()
            ):
                try:
                    os.chown(source, metadata.st_uid, metadata.st_gid)
                except PermissionError:
                    pass
        else:
            os.chmod(source, 0o600)
        os.replace(source, destination)
    except AutomationConfigurationError:
        raise
    except OSError as exc:
        raise AutomationConfigurationError(
            "Unable to save automation configuration."
        ) from exc


def _write_private_temp(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _atomic_write_json(path: Path, config: dict[str, Any]) -> None:
    try:
        payload = (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )
    except (TypeError, ValueError) as exc:
        raise AutomationConfigurationError(
            "Unable to save automation configuration."
        ) from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        _write_private_temp(temporary, payload)
        _replace_preserving_metadata(temporary, path)
        _fsync_directory(path.parent)
    except AutomationConfigurationError:
        raise
    except OSError as exc:
        raise AutomationConfigurationError(
            "Unable to save automation configuration."
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _deep_thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _deep_thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_deep_thaw(item) for item in value]
    return deepcopy(value)


class AutomationAuditLogger:
    MAX_EVENTS = MAX_AUDIT_EVENTS
    MAX_BYTES = 256 * 1024
    TAIL_READ_BYTES = 64 * 1024
    MAX_SCAN_BYTES = 256 * 1024
    MAX_LINE_BYTES = 8 * 1024
    _FIELDS = {
        "at",
        "action",
        "type",
        "policy",
        "decision",
        "status",
        "duration_ms",
        "error_code",
        "summary",
    }
    _DECISIONS = {"deny", "disabled", "approval_required", "approved", "allow"}
    _STATUSES = {"denied", "error", "success"}
    _ERROR_CODES = {
        None,
        "approval_required",
        "automation_denied",
        "automation_disabled",
        "automation_execution_failed",
        "browser_open_failed",
        "command_execution_failed",
        "command_failed",
        "command_timeout",
        "github_inspect_failed",
        "github_tool_unavailable",
        "path_identity_changed",
        "status_report_failed",
    }
    _SUMMARIES = {
        "Automation blocked by policy.",
        "Automation completed.",
        "Automation execution failed.",
    }
    _HASHED_ACTION = re.compile(r"^sha256:[0-9a-f]{12}$")

    def __init__(self, path: Path, clock: Callable[[], datetime]) -> None:
        self.path = _canonical_path(Path(path))
        self._clock = clock

    def record(
        self,
        *,
        action: str,
        automation_type: str,
        policy: str,
        decision: str,
        status: str,
        duration_ms: int,
        error_code: str | None,
        summary: str,
    ) -> None:
        event = {
            "at": _iso_timestamp(self._clock()),
            "action": self._safe_action(action),
            "type": automation_type,
            "policy": policy,
            "decision": decision,
            "status": status,
            "duration_ms": max(0, int(duration_ms)),
            "error_code": error_code,
            "summary": summary,
        }
        if not self._valid_event(event):
            raise OSError("Audit event validation failed.")
        encoded = (
            json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        with _interprocess_path_lock(self.path):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            prefix = b""
            try:
                with self.path.open("rb") as existing:
                    existing.seek(0, os.SEEK_END)
                    if existing.tell() > 0:
                        existing.seek(-1, os.SEEK_END)
                        if existing.read(1) != b"\n":
                            prefix = b"\n"
            except FileNotFoundError:
                pass
            with self.path.open("ab") as handle:
                handle.write(prefix + encoded)
                handle.flush()
                os.fsync(handle.fileno())
            self._rotate_locked()

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        if limit <= 0 or not self.path.exists():
            return []
        with _interprocess_path_lock(self.path):
            return self._tail_events_locked(min(limit, self.MAX_EVENTS))

    def _rotate_locked(self) -> None:
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        events = self._tail_events_locked(self.MAX_EVENTS + 1)
        if size <= self.MAX_BYTES and len(events) <= self.MAX_EVENTS:
            return
        events = events[-self.MAX_EVENTS :]
        payload = b"".join(
            (json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n").encode(
                "utf-8"
            )
            for event in events
        )
        while len(payload) > self.MAX_BYTES and events:
            events.pop(0)
            payload = b"".join(
                (
                    json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n"
                ).encode("utf-8")
                for event in events
            )
        temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        try:
            _write_private_temp(temporary, payload)
            _replace_preserving_metadata(temporary, self.path)
            _fsync_directory(self.path.parent)
        finally:
            temporary.unlink(missing_ok=True)

    def _tail_events_locked(self, limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        try:
            with self.path.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                end = handle.tell()
                read_size = min(end, self.MAX_SCAN_BYTES)
                start = end - read_size
                handle.seek(start)
                payload = handle.read(read_size)
        except OSError:
            return []

        lines = payload.split(b"\n")
        if start > 0 and lines:
            lines = lines[1:]
        newest: list[dict[str, Any]] = []
        for raw_line in reversed(lines):
            if not raw_line or len(raw_line) > self.MAX_LINE_BYTES:
                continue
            event = self._decode_event(raw_line)
            if event is not None:
                newest.append(event)
                if len(newest) >= limit:
                    break
        return list(reversed(newest))

    def _decode_event(self, raw_line: bytes) -> dict[str, Any] | None:
        try:
            event = json.loads(raw_line.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            return None
        return event if self._valid_event(event) else None

    def _valid_event(self, event: Any) -> bool:
        if not isinstance(event, dict) or set(event) != self._FIELDS:
            return False
        action = event["action"]
        if not isinstance(action, str) or not self._HASHED_ACTION.fullmatch(action):
            return False
        try:
            timestamp = datetime.fromisoformat(event["at"])
        except (TypeError, ValueError):
            return False
        if timestamp.tzinfo is None:
            return False
        duration = event["duration_ms"]
        if (
            not isinstance(duration, int)
            or isinstance(duration, bool)
            or duration < 0
            or duration > 86_400_000
        ):
            return False
        if (
            event["type"] not in AUTOMATION_TYPES
            or event["policy"] not in AUTOMATION_POLICIES
            or event["decision"] not in self._DECISIONS
            or event["status"] not in self._STATUSES
            or event["error_code"] not in self._ERROR_CODES
            or event["summary"] not in self._SUMMARIES
        ):
            return False
        if event["status"] == "success":
            return (
                event["decision"] in {"allow", "approved"}
                and event["error_code"] is None
                and event["summary"] == "Automation completed."
            )
        if event["status"] == "denied":
            return (
                event["decision"] in {"deny", "disabled", "approval_required"}
                and event["error_code"]
                in {"automation_denied", "automation_disabled", "approval_required"}
                and event["summary"] == "Automation blocked by policy."
            )
        return event["summary"] == "Automation execution failed."

    def _safe_action(self, action: str) -> str:
        return f"sha256:{_opaque_digest(action)}"


@dataclass(frozen=True)
class _PathGuard:
    kind: str
    target: Path
    target_identity: tuple[int, int] | None
    parent_identity: tuple[int, int]
    roots: tuple[tuple[Path, tuple[int, int]], ...]


def _path_identity(path: Path) -> tuple[int, int]:
    metadata = path.stat()
    return metadata.st_dev, metadata.st_ino


def _build_path_guard(definition: Mapping[str, Any]) -> _PathGuard:
    kind = str(definition["type"])
    roots = tuple(
        (Path(str(root)), _path_identity(Path(str(root))))
        for root in definition["allowed_roots"]
    )
    if kind == "command":
        target = Path(str(definition["cwd"]))
        target_identity = _path_identity(target)
    else:
        target = Path(str(definition["output_path"]))
        target_identity = _path_identity(target) if target.exists() else None
    return _PathGuard(
        kind=kind,
        target=target,
        target_identity=target_identity,
        parent_identity=_path_identity(target.parent),
        roots=roots,
    )


def _verify_path_guard(guard: _PathGuard) -> None:
    try:
        for root, identity in guard.roots:
            if (
                not _same_path(root.resolve(strict=True), root)
                or _path_identity(root) != identity
            ):
                raise OSError
        if guard.kind == "command":
            current = guard.target.resolve(strict=True)
            if (
                not _same_path(current, guard.target)
                or _path_identity(current) != guard.target_identity
                or _path_identity(current.parent) != guard.parent_identity
            ):
                raise OSError
        else:
            current = guard.target.resolve(strict=False)
            if (
                not _same_path(current, guard.target)
                or _path_identity(guard.target.parent) != guard.parent_identity
            ):
                raise OSError
        if not _under_any_root(guard.target, [root for root, _ in guard.roots]):
            raise OSError
    except (OSError, RuntimeError) as exc:
        raise AutomationExecutionError(
            "path_identity_changed",
            "Authorized filesystem path changed before execution.",
        ) from exc


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left)) == os.path.normcase(str(right))


@dataclass
class _CaptureBuffer:
    maximum: int
    data: bytearray
    truncated: bool = False

    def consume(self, chunk: bytes) -> None:
        remaining = self.maximum - len(self.data)
        if remaining > 0:
            self.data.extend(chunk[:remaining])
        if len(chunk) > remaining:
            self.truncated = True


class BoundedProcessRunner:
    READ_SIZE = 64 * 1024

    def run(
        self,
        argv: list[str],
        *,
        cwd: str,
        timeout: int,
        max_output_bytes: int,
    ) -> subprocess.CompletedProcess[bytes]:
        options: dict[str, Any] = {
            "cwd": cwd,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "shell": False,
        }
        if os.name == "nt":
            options["creationflags"] = getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
        else:
            options["start_new_session"] = True
        process = subprocess.Popen(argv, **options)
        stdout = _CaptureBuffer(max_output_bytes, bytearray())
        stderr = _CaptureBuffer(max_output_bytes, bytearray())
        readers = [
            threading.Thread(
                target=self._drain,
                args=(process.stdout, stdout),
                daemon=True,
            ),
            threading.Thread(
                target=self._drain,
                args=(process.stderr, stderr),
                daemon=True,
            ),
        ]
        for reader in readers:
            reader.start()
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._terminate_tree(process)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        finally:
            for reader in readers:
                reader.join(timeout=5)
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
        if timed_out:
            raise subprocess.TimeoutExpired(argv, timeout)
        completed = subprocess.CompletedProcess(
            argv,
            process.returncode,
            bytes(stdout.data),
            bytes(stderr.data),
        )
        completed.stdout_truncated = stdout.truncated  # type: ignore[attr-defined]
        completed.stderr_truncated = stderr.truncated  # type: ignore[attr-defined]
        return completed

    def _drain(self, stream: Any, capture: _CaptureBuffer) -> None:
        if stream is None:
            return
        while True:
            chunk = stream.read(self.READ_SIZE)
            if not chunk:
                return
            capture.consume(chunk)

    @staticmethod
    def _terminate_tree(process: subprocess.Popen[bytes]) -> None:
        if os.name == "nt":
            try:
                result = subprocess.run(
                    [
                        "taskkill",
                        "/PID",
                        str(process.pid),
                        "/T",
                        "/F",
                    ],
                    shell=False,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                    check=False,
                )
                if result.returncode == 0:
                    return
            except (OSError, subprocess.SubprocessError):
                pass
            try:
                os.kill(process.pid, signal.CTRL_BREAK_EVENT)
                process.wait(timeout=1)
            except (OSError, subprocess.SubprocessError):
                if process.poll() is None:
                    process.kill()
            return
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            process.kill()


class AutomationManager:
    def __init__(
        self,
        settings: Mapping[str, Mapping[str, Any]],
        home: Path,
        store: JsonStore,
        *,
        tool_manager: Any = None,
        browser_opener: Callable[[str], Any] | None = None,
        process_runner: Callable[..., Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(settings, Mapping):
            raise AutomationConfigurationError("Automation settings must be an object.")
        validated = {
            name: _validate_definition(name, definition)
            for name, definition in settings.items()
        }
        self._path_guards = {
            name: _build_path_guard(definition)
            for name, definition in validated.items()
            if definition["type"] in {"command", "status_report"}
        }
        self._settings = _deep_freeze(validated)

        self.home = Path(home)
        self.store = store
        self.tool_manager = tool_manager
        self._browser_opener = browser_opener or webbrowser.open
        self._process_runner = process_runner
        self._bounded_process_runner = BoundedProcessRunner()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._audit_logger = AutomationAuditLogger(
            self.home / "automation_audit.jsonl",
            self._clock,
        )
        self.audit_health = {"status": "healthy", "warning": None}

    @property
    def settings(self) -> Mapping[str, Mapping[str, Any]]:
        return self._settings

    def run(self, name: str, approved: bool = False) -> dict[str, Any]:
        _validate_action_name(name)
        definition = self.settings.get(name)
        if definition is None:
            raise AutomationConfigurationError(f"Unknown automation '{name}'.")

        automation_type = definition["type"]
        policy = definition["policy"]
        permission_error: AutomationPermissionError | None = None
        permission_decision: str | None = None
        if not definition["enabled"]:
            permission_decision = "disabled"
            permission_error = AutomationPermissionError(
                "automation_disabled",
                f"Automation '{name}' is disabled.",
            )
        elif policy == "deny":
            permission_decision = "deny"
            permission_error = AutomationPermissionError(
                "automation_denied",
                f"Automation '{name}' is denied by policy.",
            )
        elif policy == "ask" and not approved:
            permission_decision = "approval_required"
            permission_error = AutomationPermissionError(
                "approval_required",
                f"Automation '{name}' requires one-shot approval.",
            )
        if permission_error is not None and permission_decision is not None:
            permission_error.audit_warning = self._record_denial(
                name,
                automation_type,
                policy,
                permission_decision,
                permission_error.code,
            )
            raise permission_error

        decision = "approved" if policy == "ask" else "allow"
        started = monotonic()
        try:
            data = self._execute(name, definition)
        except AutomationExecutionError as exc:
            exc.audit_warning = self._record_audit(
                action=name,
                automation_type=automation_type,
                policy=policy,
                decision=decision,
                status="error",
                duration_ms=_duration_ms(started),
                error_code=exc.code,
                summary="Automation execution failed.",
            )
            raise
        except Exception as exc:
            failure = AutomationExecutionError(
                "automation_execution_failed",
                "Automation execution failed.",
            )
            failure.audit_warning = self._record_audit(
                action=name,
                automation_type=automation_type,
                policy=policy,
                decision=decision,
                status="error",
                duration_ms=_duration_ms(started),
                error_code=failure.code,
                summary="Automation execution failed.",
            )
            raise failure from exc

        audit_warning = self._record_audit(
            action=name,
            automation_type=automation_type,
            policy=policy,
            decision=decision,
            status="success",
            duration_ms=_duration_ms(started),
            error_code=None,
            summary="Automation completed.",
        )
        result = {
            "action": name,
            "type": automation_type,
            "status": "success",
            "at": _iso_timestamp(self._clock()),
            **data,
        }
        if audit_warning is not None:
            result["audit_warning"] = audit_warning
        return result

    def audit_events(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._audit_logger.recent(limit)

    def _execute(
        self,
        name: str,
        definition: Mapping[str, Any],
    ) -> dict[str, Any]:
        automation_type = definition["type"]
        if automation_type in {"command", "status_report"}:
            _verify_path_guard(self._path_guards[name])
        if automation_type == "browser":
            return self._run_browser(definition)
        if automation_type == "command":
            return self._run_command(definition)
        if automation_type == "github_inspect":
            return self._run_github_inspect(definition)
        return self._run_status_report(definition, self._path_guards[name])

    def _run_browser(self, definition: dict[str, Any]) -> dict[str, Any]:
        url = definition["url"]
        host = _parsed_browser_url(url).hostname
        try:
            opened = self._browser_opener(url)
        except Exception as exc:
            raise AutomationExecutionError(
                "browser_open_failed",
                "Browser automation failed.",
            ) from exc
        if opened is False:
            raise AutomationExecutionError(
                "browser_open_failed",
                "Browser automation failed.",
            )
        return {"host": host}

    def _run_command(self, definition: dict[str, Any]) -> dict[str, Any]:
        argv = list(definition["argv"])
        cwd = str(definition["cwd"])
        try:
            if self._process_runner is None:
                completed = self._bounded_process_runner.run(
                    argv,
                    cwd=cwd,
                    timeout=definition["timeout_seconds"],
                    max_output_bytes=definition["max_output_bytes"],
                )
            else:
                completed = self._process_runner(
                    argv,
                    cwd=cwd,
                    shell=False,
                    timeout=definition["timeout_seconds"],
                    capture_output=True,
                    check=False,
                )
        except subprocess.TimeoutExpired as exc:
            raise AutomationExecutionError(
                "command_timeout",
                "Command automation timed out.",
            ) from exc
        except Exception as exc:
            raise AutomationExecutionError(
                "command_execution_failed",
                "Command automation failed to start.",
            ) from exc

        try:
            returncode = int(completed.returncode)
        except (AttributeError, TypeError, ValueError) as exc:
            raise AutomationExecutionError(
                "command_execution_failed",
                "Command automation returned an invalid result.",
            ) from exc
        if returncode != 0:
            raise AutomationExecutionError(
                "command_failed",
                "Command automation exited unsuccessfully.",
            )

        stdout, stdout_was_truncated = _bounded_output(
            getattr(completed, "stdout", b""),
            definition["max_output_bytes"],
        )
        stderr, stderr_was_truncated = _bounded_output(
            getattr(completed, "stderr", b""),
            definition["max_output_bytes"],
        )
        stdout_truncated = bool(
            getattr(completed, "stdout_truncated", False) or stdout_was_truncated
        )
        stderr_truncated = bool(
            getattr(completed, "stderr_truncated", False) or stderr_was_truncated
        )
        return {
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }

    def _run_github_inspect(self, definition: dict[str, Any]) -> dict[str, Any]:
        if self.tool_manager is None:
            raise AutomationExecutionError(
                "github_tool_unavailable",
                "GitHub inspection is unavailable.",
            )
        arguments = {"limit": definition["limit"]}
        if definition.get("repo"):
            arguments["repo"] = definition["repo"]
        try:
            result = self.tool_manager.execute("github", "read", **arguments)
            data = result.data
        except Exception as exc:
            raise AutomationExecutionError(
                "github_inspect_failed",
                "GitHub inspection failed.",
            ) from exc
        if not isinstance(data, Mapping):
            raise AutomationExecutionError(
                "github_inspect_failed",
                "GitHub inspection returned an invalid result.",
            )
        return _normalized_github_metadata(data, definition["limit"])

    def _run_status_report(
        self,
        definition: Mapping[str, Any],
        guard: _PathGuard,
    ) -> dict[str, Any]:
        try:
            state = self.store.load()
            report = _status_markdown(state, self._clock())
            output_path = Path(str(definition["output_path"]))
            _atomic_write_text(output_path, report, guard)
        except (AutomationConfigurationError, AutomationExecutionError):
            raise
        except Exception as exc:
            raise AutomationExecutionError(
                "status_report_failed",
                "Status report generation failed.",
            ) from exc
        return {"bytes_written": len(report.encode("utf-8"))}

    def _record_denial(
        self,
        name: str,
        automation_type: str,
        policy: str,
        decision: str,
        error_code: str,
    ) -> str | None:
        return self._record_audit(
            action=name,
            automation_type=automation_type,
            policy=policy,
            decision=decision,
            status="denied",
            duration_ms=0,
            error_code=error_code,
            summary="Automation blocked by policy.",
        )

    def _record_audit(self, **fields: Any) -> str | None:
        try:
            self._audit_logger.record(**fields)
        except Exception:
            warning = "audit_write_failed"
            self.audit_health = {"status": "degraded", "warning": warning}
            return warning
        return None


def _validate_definition(name: str, value: Any) -> dict[str, Any]:
    _validate_action_name(name)
    if not isinstance(value, Mapping):
        raise AutomationConfigurationError(f"Automation '{name}' must be an object.")
    definition = deepcopy(dict(value))
    automation_type = definition.get("type")
    if automation_type not in AUTOMATION_TYPES:
        raise AutomationConfigurationError(
            f"Automation '{name}' has an unsupported type."
        )
    unknown_fields = set(definition).difference(_TYPE_FIELDS[automation_type])
    if unknown_fields:
        raise AutomationConfigurationError(
            f"Automation '{name}' contains unsupported fields."
        )

    enabled = definition.get("enabled", True)
    policy = definition.get("policy", "ask")
    if not isinstance(enabled, bool):
        raise AutomationConfigurationError("Automation enabled must be boolean.")
    if policy not in AUTOMATION_POLICIES:
        raise AutomationConfigurationError(
            "Automation policy must be deny, ask, or allow."
        )
    definition["enabled"] = enabled
    definition["policy"] = policy

    if automation_type == "browser":
        parsed = _parsed_browser_url(definition.get("url"))
        allowed_hosts = definition.get("allowed_hosts", [])
        if (
            not isinstance(allowed_hosts, list)
            or not allowed_hosts
            or not all(
                isinstance(host, str) and _valid_allowed_host(host)
                for host in allowed_hosts
            )
        ):
            raise AutomationConfigurationError(
                "Browser allowed_hosts must be a nonempty list of hostnames."
            )
        normalized_hosts = [host.rstrip(".").casefold() for host in allowed_hosts]
        if not any(
            _host_allowed(parsed.hostname or "", allowed)
            for allowed in normalized_hosts
        ):
            raise AutomationConfigurationError(
                "Browser URL host is outside allowed_hosts."
            )
        definition["allowed_hosts"] = normalized_hosts
    elif automation_type == "command":
        _validate_command_definition(definition)
    elif automation_type == "github_inspect":
        repo = definition.get("repo")
        if repo is not None and (
            not isinstance(repo, str)
            or not repo.strip()
            or len(repo) > 200
            or _has_control_or_whitespace(repo)
        ):
            raise AutomationConfigurationError(
                "GitHub repo must be a bounded nonempty string."
            )
        limit = definition.get("limit", 20)
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit < 1
            or limit > MAX_GITHUB_LIMIT
        ):
            raise AutomationConfigurationError(
                f"GitHub limit must be between 1 and {MAX_GITHUB_LIMIT}."
            )
        definition["limit"] = limit
    else:
        _validate_status_definition(definition)
    return definition


def _validate_action_name(name: Any) -> None:
    if not isinstance(name, str) or not ACTION_NAME_PATTERN.fullmatch(name):
        raise AutomationConfigurationError(
            "Automation name must use letters, numbers, '.', '_', or '-'."
        )


def _parsed_browser_url(value: Any):
    if not isinstance(value, str) or not value or _has_control_or_whitespace(value):
        raise AutomationConfigurationError(
            "Browser URL must be a fixed HTTP or HTTPS URL."
        )
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as exc:
        raise AutomationConfigurationError("Browser URL is invalid.") from exc
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise AutomationConfigurationError(
            "Browser URL requires HTTP or HTTPS, a hostname, and no credentials."
        )
    return parsed


def _valid_allowed_host(host: str) -> bool:
    normalized = host.rstrip(".")
    if (
        not normalized
        or len(normalized) > 253
        or _has_control_or_whitespace(normalized)
        or "/" in normalized
        or ":" in normalized
        or "@" in normalized
        or normalized.startswith(".")
        or normalized.endswith(".")
    ):
        return False
    return all(
        part
        and len(part) <= 63
        and not part.startswith("-")
        and not part.endswith("-")
        and all(character.isalnum() or character == "-" for character in part)
        for part in normalized.split(".")
    )


def _host_allowed(host: str, allowed: str) -> bool:
    normalized = host.rstrip(".").casefold()
    return normalized == allowed or normalized.endswith(f".{allowed}")


def _validate_command_definition(definition: dict[str, Any]) -> None:
    argv = definition.get("argv")
    if (
        not isinstance(argv, list)
        or not argv
        or not all(isinstance(item, str) and item for item in argv)
        or any("\x00" in item for item in argv)
    ):
        raise AutomationConfigurationError(
            "Command argv must be a nonempty list of nonempty strings."
        )
    timeout = definition.get("timeout_seconds", 30)
    max_output = definition.get("max_output_bytes", 65_536)
    if (
        not isinstance(timeout, int)
        or isinstance(timeout, bool)
        or timeout < 1
        or timeout > 300
    ):
        raise AutomationConfigurationError(
            "Command timeout_seconds must be between 1 and 300."
        )
    if (
        not isinstance(max_output, int)
        or isinstance(max_output, bool)
        or max_output < 1
        or max_output > MAX_COMMAND_OUTPUT_BYTES
    ):
        raise AutomationConfigurationError(
            f"Command max_output_bytes must be between 1 and {MAX_COMMAND_OUTPUT_BYTES}."
        )
    definition["timeout_seconds"] = timeout
    definition["max_output_bytes"] = max_output
    cwd = _resolved_command_cwd(definition)
    roots = _resolved_allowed_roots(definition.get("allowed_roots"))
    definition["cwd"] = str(cwd)
    definition["allowed_roots"] = [str(root) for root in roots]


def _validate_status_definition(definition: dict[str, Any]) -> None:
    output_path = definition.get("output_path")
    if not isinstance(output_path, str) or not output_path:
        raise AutomationConfigurationError("Status report output_path is required.")
    if Path(output_path).suffix.casefold() != ".md":
        raise AutomationConfigurationError(
            "Status report output_path must use the .md extension."
        )
    output = _resolved_report_path(definition)
    roots = _resolved_allowed_roots(definition.get("allowed_roots"))
    definition["output_path"] = str(output)
    definition["allowed_roots"] = [str(root) for root in roots]


def _resolved_command_cwd(definition: Mapping[str, Any]) -> Path:
    cwd_value = definition.get("cwd")
    if not isinstance(cwd_value, str) or not cwd_value:
        raise AutomationConfigurationError("Command cwd is required.")
    try:
        cwd = Path(cwd_value).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise AutomationConfigurationError(
            "Command cwd must be an existing directory."
        ) from exc
    if not cwd.is_dir():
        raise AutomationConfigurationError("Command cwd must be an existing directory.")
    roots = _resolved_allowed_roots(definition.get("allowed_roots"))
    if not _under_any_root(cwd, roots):
        raise AutomationConfigurationError("Command cwd is outside allowed_roots.")
    return cwd


def _resolved_report_path(definition: Mapping[str, Any]) -> Path:
    output_value = definition.get("output_path")
    if not isinstance(output_value, str) or not output_value:
        raise AutomationConfigurationError("Status report output_path is required.")
    output = Path(output_value).resolve(strict=False)
    roots = _resolved_allowed_roots(definition.get("allowed_roots"))
    if not _under_any_root(output, roots):
        raise AutomationConfigurationError(
            "Status report output_path is outside allowed_roots."
        )
    if not output.parent.is_dir():
        raise AutomationConfigurationError(
            "Status report output parent must be an existing directory."
        )
    return output


def _resolved_allowed_roots(value: Any) -> list[Path]:
    if (
        not isinstance(value, list)
        or not value
        or len(value) > 32
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise AutomationConfigurationError(
            "allowed_roots must be a nonempty list of paths."
        )
    roots: list[Path] = []
    for item in value:
        try:
            root = Path(item).resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise AutomationConfigurationError(
                "Each allowed root must be an existing directory."
            ) from exc
        if not root.is_dir():
            raise AutomationConfigurationError(
                "Each allowed root must be an existing directory."
            )
        roots.append(root)
    return roots


def _under_any_root(path: Path, roots: list[Path]) -> bool:
    candidate = os.path.normcase(str(path))
    for root in roots:
        normalized_root = os.path.normcase(str(root))
        try:
            common = os.path.commonpath((candidate, normalized_root))
        except ValueError:
            continue
        if os.path.normcase(common) == normalized_root:
            return True
    return False


def _bounded_output(value: Any, maximum: int) -> tuple[str, bool]:
    if value is None:
        raw = b""
    elif isinstance(value, bytes):
        raw = value
    elif isinstance(value, str):
        raw = value.encode("utf-8")
    else:
        raw = str(value).encode("utf-8")
    bounded = raw[:maximum]
    return bounded.decode("utf-8", errors="replace"), len(raw) > maximum


def _normalized_github_metadata(
    data: Mapping[str, Any],
    limit: int,
) -> dict[str, Any]:
    issues = data.get("issues")
    normalized_issues: list[dict[str, Any]] = []
    if isinstance(issues, list):
        for issue in issues[:limit]:
            if not isinstance(issue, Mapping):
                continue
            normalized_issues.append(
                {
                    "number": _safe_integer(issue.get("number")),
                    "title": _bounded_string(issue.get("title"), 500),
                    "updated_at": _bounded_string(issue.get("updated_at"), 100),
                }
            )
    return {
        "repository": _bounded_string(data.get("repository"), 200),
        "description": _bounded_string(data.get("description"), 1_000),
        "default_branch": _bounded_string(data.get("default_branch"), 200),
        "stars": _safe_integer(data.get("stars")),
        "forks": _safe_integer(data.get("forks")),
        "open_issues": _safe_integer(data.get("open_issues")),
        "issues": normalized_issues,
    }


def _status_markdown(state: Mapping[str, Any], now: datetime) -> str:
    memories = state.get("memories")
    goals = state.get("goals")
    tasks = state.get("daily_tasks")
    memory_items = memories if isinstance(memories, list) else []
    goal_items = goals if isinstance(goals, list) else []
    task_items = tasks if isinstance(tasks, list) else []

    active_goals = [
        item
        for item in goal_items
        if isinstance(item, Mapping) and item.get("status", "active") == "active"
    ]
    active_goal_ids = sorted(
        f"goal-{_opaque_digest(item.get('id'))}" for item in active_goals
    )
    task_counts = {status: 0 for status in _TASK_STATUSES}
    unknown_tasks = 0
    for item in task_items:
        status = item.get("status") if isinstance(item, Mapping) else None
        if status in task_counts:
            task_counts[status] += 1
        else:
            unknown_tasks += 1

    runtime = state.get("runtime")
    runs = runtime.get("job_runs") if isinstance(runtime, Mapping) else []
    safe_runs = [
        _safe_scheduler_run(run)
        for run in (runs[-10:] if isinstance(runs, list) else [])
        if isinstance(run, Mapping)
    ]

    lines = [
        "# Nexus Status Report",
        "",
        f"Generated: {_iso_timestamp(now)}",
        "",
        "## Counts",
        "",
        f"- Memories: {len(memory_items)}",
        f"- Goals: {len(goal_items)}",
        f"- Active goals: {len(active_goals)}",
        f"- Daily tasks: {len(task_items)}",
        "",
        "## Active Goals",
        "",
    ]
    lines.extend([f"- `{goal_id}`" for goal_id in active_goal_ids] or ["- None"])
    lines.extend(["", "## Task Statuses", ""])
    lines.extend(f"- {status}: {task_counts[status]}" for status in _TASK_STATUSES)
    lines.append(f"- unknown: {unknown_tasks}")
    lines.extend(
        [
            "",
            "## Recent Scheduler Runs",
            "",
            "Run | Job | Trigger | Local date | Status | Error",
            "--- | --- | --- | --- | --- | ---",
        ]
    )
    if safe_runs:
        lines.extend(
            " | ".join(
                (
                    run["run"],
                    run["job"],
                    run["trigger"],
                    run["local_date"],
                    run["status"],
                    run["error_code"],
                )
            )
            for run in safe_runs
        )
    else:
        lines.append("none | none | none | none | none | none")
    return "\n".join(lines) + "\n"


def _safe_scheduler_run(run: Mapping[str, Any]) -> dict[str, str]:
    job = run.get("job")
    trigger = run.get("trigger")
    status = run.get("status")
    local_date = run.get("local_date")
    run_identifier = run.get("id")
    if not isinstance(run_identifier, str) or not run_identifier:
        run_identifier = json.dumps(
            {
                key: run.get(key)
                for key in ("job", "trigger", "local_date", "status", "started_at")
            },
            ensure_ascii=True,
            sort_keys=True,
            default=str,
        )
    return {
        "run": f"run-{_opaque_digest(run_identifier)}",
        "job": job if job in RUNTIME_JOB_NAMES else "unknown",
        "trigger": trigger if trigger in {"scheduled", "manual"} else "unknown",
        "local_date": (
            local_date
            if isinstance(local_date, str)
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", local_date)
            else "unknown"
        ),
        "status": (
            status
            if status in {"running", "success", "partial", "error"}
            else "unknown"
        ),
        "error_code": "none"
        if run.get("error_code") is None
        else "job_execution_failed",
    }


def _atomic_write_text(path: Path, text: str, guard: _PathGuard) -> None:
    _verify_path_guard(guard)
    temporary = guard.target.parent / f".{guard.target.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        _verify_path_guard(guard)
        # Cross-platform path APIs cannot close the final local-owner swap race.
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _opaque_digest(value: Any) -> str:
    encoded = str(value if value is not None else "unknown").encode(
        "utf-8", errors="replace"
    )
    return hashlib.sha256(encoded).hexdigest()[:12]


def _safe_identifier(value: Any) -> str:
    if isinstance(value, str) and SAFE_IDENTIFIER_PATTERN.fullmatch(value):
        return value
    return "unknown"


def _safe_integer(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return max(0, min(value, 2_147_483_647))
    return 0


def _bounded_string(value: Any, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    return value[:maximum]


def _has_control_or_whitespace(value: str) -> bool:
    return any(character.isspace() or ord(character) < 32 for character in value)


def _iso_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(microsecond=0).isoformat()


def _duration_ms(started: float) -> int:
    return max(0, int((monotonic() - started) * 1_000))
