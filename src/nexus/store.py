from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from .file_lock import path_transaction


DEFAULT_STATE = {
    "memories": [],
    "goals": [],
    "daily_tasks": [],
    "habits": [],
    "projects": [],
    "research_projects": [],
    "suggestions": [],
    "rag_index": None,
    "runtime": {
        "job_runs": [],
        "occurrence_claims": {},
    },
}

_PATH_LOCKS: dict[str, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()
_MISSING_REVISION = object()
MutationResult = TypeVar("MutationResult")


class StateConflictError(RuntimeError):
    """Raised when a stale state snapshot would overwrite newer data."""


class StoreState(dict[str, Any]):
    """State mapping carrying non-persisted revision and merge base data."""

    def __init__(
        self,
        *args: Any,
        revision: str | None,
        base: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.revision = revision
        self.base = deepcopy(base)


def _shared_path_lock(path: Path) -> threading.RLock:
    key = str(path.absolute()).casefold()
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


@dataclass
class JsonStore:
    path: Path

    @classmethod
    def from_env(cls) -> "JsonStore":
        root = Path(os.environ.get("NEXUS_HOME", ".nexus"))
        return cls(root / "state.json")

    def load(self) -> StoreState:
        with _shared_path_lock(self.path), path_transaction(self.path):
            payload = self._read_payload()
        if payload is None:
            state = self._default_state()
            return StoreState(state, revision=None, base=state)

        state = self._decode(payload)
        return StoreState(state, revision=self._revision(payload), base=state)

    def save(self, state: dict[str, Any]) -> None:
        expected_revision = getattr(state, "revision", _MISSING_REVISION)
        with _shared_path_lock(self.path), path_transaction(self.path):
            current_payload = self._read_payload()
            current_revision = (
                self._revision(current_payload) if current_payload is not None else None
            )
            current_state = (
                self._decode(current_payload)
                if current_payload is not None
                else self._default_state()
            )
            saved_state = self._normalize(dict(state))
            if expected_revision is _MISSING_REVISION:
                if current_payload is not None:
                    raise StateConflictError(
                        "State changed before this unversioned save."
                    )
            elif expected_revision != current_revision:
                base = getattr(state, "base", _MISSING_REVISION)
                if base is _MISSING_REVISION:
                    raise StateConflictError("State changed since it was loaded.")
                caller_changes = self._changed_keys(base, saved_state)
                current_changes = self._changed_keys(base, current_state)
                if caller_changes.intersection(current_changes):
                    raise StateConflictError("State changed since it was loaded.")
                saved_state = self._apply_changes(
                    current_state,
                    saved_state,
                    caller_changes,
                )
            payload = self._encode(saved_state)
            self._atomic_write(payload)
            if isinstance(state, StoreState):
                state.clear()
                state.update(deepcopy(saved_state))
                state.revision = self._revision(payload)
                state.base = deepcopy(saved_state)

    def mutate(
        self,
        callback: Callable[[StoreState], MutationResult],
        *,
        retries: int = 3,
    ) -> MutationResult:
        if not isinstance(retries, int) or isinstance(retries, bool) or retries < 1:
            raise ValueError("retries must be a positive integer.")
        for attempt in range(retries):
            state = self.load()
            result = callback(state)
            try:
                self.save(state)
            except StateConflictError:
                if attempt + 1 >= retries:
                    raise
                continue
            return result
        raise StateConflictError("State changed during every mutation attempt.")

    def _atomic_write(self, payload: bytes) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def _read_payload(self) -> bytes | None:
        try:
            return self.path.read_bytes()
        except FileNotFoundError:
            return None

    @staticmethod
    def _encode(state: dict[str, Any]) -> bytes:
        text = json.dumps(dict(state), ensure_ascii=False, indent=2)
        return f"{text}\n".encode("utf-8")

    def _decode(self, payload: bytes) -> dict[str, Any]:
        return self._normalize(json.loads(payload.decode("utf-8")))

    def _normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        state = self._default_state()
        state.update(deepcopy(data))
        runtime = self._default_state()["runtime"]
        stored_runtime = data.get("runtime")
        if isinstance(stored_runtime, dict):
            runtime.update(deepcopy(stored_runtime))
        state["runtime"] = runtime
        return state

    @staticmethod
    def _changed_keys(
        base: dict[str, Any],
        updated: dict[str, Any],
    ) -> set[str]:
        missing = object()
        return {
            key
            for key in set(base).union(updated)
            if base.get(key, missing) != updated.get(key, missing)
        }

    @staticmethod
    def _apply_changes(
        current: dict[str, Any],
        caller: dict[str, Any],
        changed_keys: set[str],
    ) -> dict[str, Any]:
        merged = deepcopy(current)
        for key in changed_keys:
            if key in caller:
                merged[key] = deepcopy(caller[key])
            else:
                merged.pop(key, None)
        return merged

    @staticmethod
    def _revision(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _default_state() -> dict[str, Any]:
        return json.loads(json.dumps(DEFAULT_STATE))
