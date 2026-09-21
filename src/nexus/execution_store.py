from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


class ExecutionBusyError(RuntimeError):
    """The run lease is held by another executor."""


class ExecutionStore:
    """Local snapshots; a separate OS lease serializes runners without blocking controls."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, state TEXT NOT NULL, control TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS task_sessions (name TEXT PRIMARY KEY, run_id TEXT, candidates TEXT NOT NULL, revision INTEGER NOT NULL)")

    @staticmethod
    def validate_session(name):
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
            raise ValueError("Invalid task session name.")

    def task_session(self, name):
        self.validate_session(name)
        with self.connect() as db:
            row = db.execute("SELECT run_id,candidates,revision FROM task_sessions WHERE name=?", (name,)).fetchone()
        return {"run_id": row[0], "candidates": json.loads(row[1]), "revision": row[2]} if row else {
            "run_id": None, "candidates": [], "revision": 0}

    def update_task_session(self, name, revision, *, run_id, candidates):
        self.validate_session(name)
        if type(revision) is not int or revision < 0 or not isinstance(candidates, list) or len(candidates) > 5:
            raise ValueError("Invalid task session update.")
        for key in [*candidates, *([run_id] if run_id is not None else [])]:
            self.get(key)
        if len(set(candidates)) != len(candidates):
            raise ValueError("Duplicate task candidates.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision FROM task_sessions WHERE name=?", (name,)).fetchone()
            if (row[0] if row else 0) != revision:
                raise ValueError("Task session changed; inspect the selection again.")
            db.execute("INSERT INTO task_sessions(name,run_id,candidates,revision) VALUES (?,?,?,?) "
                       "ON CONFLICT(name) DO UPDATE SET run_id=excluded.run_id,candidates=excluded.candidates,revision=excluded.revision",
                       (name, run_id, json.dumps(candidates), revision + 1))
        return {"run_id": run_id, "candidates": list(candidates), "revision": revision + 1}

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def validate_id(run_id):
        if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise ValueError("Invalid execution ID.")

    def create(self, state):
        state = {**state, "run_id": uuid4().hex, "created_at": datetime.now(timezone.utc).isoformat()}
        with self.connect() as db:
            db.execute("INSERT INTO runs(id,state) VALUES (?,?)", (state["run_id"], json.dumps(state, allow_nan=False)))
        return state

    def get(self, run_id):
        self.validate_id(run_id)
        with self.connect() as db:
            row = db.execute("SELECT state,control FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise ValueError("Execution not found.")
        return {**json.loads(row[0]), "control_requested": row[1]}

    def save(self, state):
        self.validate_id(state["run_id"])
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(state, allow_nan=False)
        if len(payload.encode()) > 8 * 1024 * 1024:
            raise ValueError("Execution snapshot exceeds 8 MiB.")
        with self.connect() as db:
            if db.execute("UPDATE runs SET state=? WHERE id=?", (payload, state["run_id"])).rowcount != 1:
                raise ValueError("Execution not found.")

    def list(self):
        with self.connect() as db:
            rows = db.execute("SELECT id,state,control FROM runs ORDER BY rowid DESC LIMIT 100").fetchall()
        return [{"run_id": key, "status": json.loads(value)["status"], "goal": json.loads(value)["goal"],
                 "control_requested": control} for key, value, control in rows]

    def request(self, run_id, request):
        self.get(run_id)
        if request not in {None, "pause", "cancel"}:
            raise ValueError("Unknown execution control.")
        with self.connect() as db:
            # Cancellation cannot be erased by a concurrent resume or pause.
            db.execute("UPDATE runs SET control=? WHERE id=? AND (control IS NULL OR control!='cancel')",
                       (request, run_id))

    def request_task_control(self, run_id, request):
        self.request(run_id, request)
        if request != "cancel":
            return
        try:
            with self.lease(run_id):
                self._acknowledge_cancel_locked(run_id)
        except ExecutionBusyError:
            # The active runner observes the sticky control at its next checkpoint.
            return

    def _acknowledge_cancel_locked(self, run_id):
        """Caller must hold the run lease; preserve unknown side-effect outcomes."""
        state = self.get(run_id)
        if state["control_requested"] != "cancel" or state["status"] in {"reported_complete", "failed", "cancelled"}:
            return state
        if state.get("phase") == "tool_running" or state["status"] == "needs_review":
            state.update(status="needs_review", summary="Tool outcome is uncertain; cancellation does not undo it.")
        else:
            state.update(status="cancelled", summary="Task cancelled; completed actions were not undone.")
        state.pop("approval_token", None)
        state.pop("approval_token_binding", None)
        self.save(state)
        return state

    @contextmanager
    def lease(self, run_id):
        self.validate_id(run_id)
        path = self.path.parent / f".executor-{run_id}.lock"
        with path.open("a+b") as handle:
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise ExecutionBusyError("Execution is already running.") from error
            try:
                yield
            finally:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)


class PersistentExecutor:
    def __init__(self, store, runtime, *, context_builder=None, verifier=None):
        self.store = store
        self.runtime = runtime
        self.context_builder = context_builder
        self.verifier = verifier

    def start(self, goal, *, max_steps=12, timeout_seconds=120, context_options=None, on_created=None, acceptance=None):
        from nexus.execution_runtime import validate_execution_request
        from nexus.execution_metrics import new_metrics

        validate_execution_request(goal, max_steps, timeout_seconds)
        context = {}
        if acceptance is not None:
            from nexus.execution_verification import validate_acceptance

            context["acceptance"] = validate_acceptance(acceptance)
        if context_options is not None:
            if self.context_builder is None:
                raise ValueError("Execution context builder is required.")
            context["context"] = self.context_builder.build(goal, **context_options)
        state = self.store.create({"goal": goal, "status": "created", "steps": 0, "observations": [],
                                   "pending_action": None, "summary": "", "verification": "not_verified", "metrics": new_metrics(),
                                   "max_steps": max_steps, "timeout_seconds": timeout_seconds, **context})
        if on_created is not None:
            on_created(state["run_id"])
        return self.resume(state["run_id"])

    def checkpoint(self, state):
        if state["status"] == "cancelled":
            self.store.request(state["run_id"], "cancel")
            state["control_requested"] = "cancel"
        if state["status"] == "waiting_approval":
            # Each approval belongs to this run and this occurrence, not a reusable permission.
            if state.get("approval_token_binding") != state["approval_binding"] or not state.get("approval_token"):
                state["approval_token"] = uuid4().hex
                state["approval_token_binding"] = state["approval_binding"]
        else:
            state.pop("approval_token", None)
            state.pop("approval_token_binding", None)
        self.store.save(state)

    def resolve(self, run_id, *, outcome, note):
        if outcome not in {"completed", "not-executed"} or not isinstance(note, str) or not note.strip() or len(note) > 4000:
            raise ValueError("An explicit outcome and a note of 1 to 4,000 characters are required.")
        with self.store.lease(run_id):
            state = self.store.get(run_id)
            if state.get("phase") != "tool_running" or not state.get("pending_action"):
                raise ValueError("No uncertain tool action to reconcile.")
            action = state["pending_action"]
            state["observations"].append({"number": len(state["observations"]) + 1, "tool": action["tool"],
                                          "status": "user_reconciled", "outcome": outcome, "data": {"note": note}})
            if outcome == "completed":
                state.update(pending_action=None, phase="idle")
            else:
                fingerprint = json.dumps([action["tool"], action["arguments"]], sort_keys=True, allow_nan=False)
                state["repeats"][fingerprint] = max(0, state["repeats"].get(fingerprint, 0) - 1)
                state["phase"] = "tool_pending"
            state.update(status="cancelled" if state["control_requested"] == "cancel" else "paused",
                         summary="User reconciled the uncertain action; no tool was executed.")
            self.checkpoint(state)
            return state

    def resume(self, run_id, *, approval_token=None, answer=None):
        with self.store.lease(run_id):
            state = self.store.get(run_id)
            if "metrics" in state and any(e["status"] == "pending" for e in state["metrics"]["attempts"]):
                from nexus.execution_metrics import recover_pending

                recover_pending(state["metrics"])
                self.store.save(state)
            if state.get("phase") == "tool_running":
                state.update(status="needs_review", summary="Tool outcome is uncertain; automatic replay is blocked.")
                self.store.save(state)
                return state
            if state["status"] in {"reported_complete", "failed", "cancelled", "needs_review", "repeated_action"}:
                raise ValueError("This execution cannot be resumed.")
            if state["control_requested"] == "cancel":
                state["status"] = "cancelled"
                self.checkpoint(state)
                return state
            validate_context = None
            if "context" in state:
                if self.context_builder is None:
                    raise ValueError("Execution context validation is required for this run.")
                validate_context = lambda: self.context_builder.validate(state["context"])
                validate_context()
            approved = None
            if state["status"] == "waiting_approval":
                if not approval_token or approval_token != state.get("approval_token"):
                    raise ValueError("Supply the exact approval_token shown for this pending action.")
                action = state["pending_action"]
                current = self.runtime.registry.binding(action["tool"], action["arguments"])
                if current != state["approval_binding"]:
                    state["approval_binding"] = current
                    self.checkpoint(state)
                    raise ValueError("Tool configuration changed. Inspect and approve the new binding.")
                approved = current
            elif approval_token:
                raise ValueError("There is no pending approval.")
            if state["status"] == "waiting_input":
                if not isinstance(answer, str) or not answer.strip() or len(answer) > 4000:
                    raise ValueError("An answer of 1 to 4,000 characters is required.")
                state.setdefault("user_answers", []).append(answer)
                state["pending_action"] = None
                state["phase"] = "idle"
            elif answer is not None:
                raise ValueError("There is no pending question.")
            self.store.request(run_id, None)
            self.runtime.run(state["goal"], max_steps=state["max_steps"],
                                    timeout_seconds=state["timeout_seconds"], initial_state=state,
                                    checkpoint=self.checkpoint,
                                    control=lambda: self.store.get(run_id)["control_requested"],
                                    context_validator=validate_context,
                                    approval_binding=approved)
            result = self.store._acknowledge_cancel_locked(run_id)
            if result["status"] == "reported_complete" and "acceptance" in result:
                return self._verify_locked(result)
            return result

    def verify(self, run_id):
        with self.store.lease(run_id):
            state = self.store.get(run_id)
            if state["status"] != "reported_complete" or "acceptance" not in state:
                raise ValueError("Only completed runs with predeclared acceptance can be checked.")
            return self._verify_locked(state)

    def _verify_locked(self, state):
        from nexus.execution_verification import FileVerifier, validate_acceptance

        acceptance = validate_acceptance(state["acceptance"])
        verifier = self.verifier
        if verifier is None:
            if self.runtime is None:
                raise ValueError("A verifier is required.")
            verifier = FileVerifier(self.runtime.registry)
        if "verification_total_seconds" not in state:
            state["verification_total_seconds"] = sum(r.get("duration_seconds", 0) for r in
                [*state.get("verification_history", []), state.get("verification_report", {})])
        previous = state.pop("verification_report", None)
        if previous is not None:
            state["verification_history"] = (state.get("verification_history", []) + [previous])[-10:]
        state["verification"] = "pending_file_checks"
        self.store.save(state)
        state["verification_report"] = verifier.verify(acceptance)
        state["verification_total_seconds"] += state["verification_report"].get("duration_seconds", 0)
        state["verification"] = "file_conditions_" + state["verification_report"]["status"]
        self.store.save(state)
        return state
