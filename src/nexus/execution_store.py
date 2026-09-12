from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


class ExecutionStore:
    """Local snapshots; a separate OS lease serializes runners without blocking controls."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, state TEXT NOT NULL, control TEXT)")

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
                raise RuntimeError("Execution is already running.") from error
            try:
                yield
            finally:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)


class PersistentExecutor:
    def __init__(self, store, runtime):
        self.store = store
        self.runtime = runtime

    def start(self, goal, *, max_steps=12, timeout_seconds=120):
        state = self.store.create({"goal": goal, "status": "created", "steps": 0, "observations": [],
                                   "pending_action": None, "summary": "", "verification": "not_verified",
                                   "max_steps": max_steps, "timeout_seconds": timeout_seconds})
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
            return self.runtime.run(state["goal"], max_steps=state["max_steps"],
                                    timeout_seconds=state["timeout_seconds"], initial_state=state,
                                    checkpoint=self.checkpoint,
                                    control=lambda: self.store.get(run_id)["control_requested"],
                                    approval_binding=approved)
