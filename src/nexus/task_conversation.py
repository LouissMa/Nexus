from __future__ import annotations

import re
import sqlite3


_CONTROLS = {
    "status": {"查看进度", "任务进度", "现在到哪一步了", "status", "progress", "show progress"},
    "list": {"任务列表", "查看任务", "list tasks", "tasks"},
    "resume": {"继续任务", "继续这个任务", "继续", "continue", "continue task", "resume"},
    "pause": {"暂停任务", "暂停", "pause", "pause task"},
    "cancel": {"取消任务", "取消", "cancel", "cancel task"},
}
_NEXT = {
    "created": ("Task created; ready to continue.", "continue"),
    "running": ("Task was last recorded as running. Controls are cooperative.", "wait"),
    "waiting_input": ("Waiting for your answer.", "answer"),
    "waiting_approval": ("Text approval required. Inspect the pending action with executor show, then use its exact approval token in executor resume.", "text_approval"),
    "needs_review": ("The tool outcome is uncertain. Inspect the destination before manual reconciliation; do not replay blindly.", "manual_review"),
    "paused": ("Task is paused.", "continue"),
    "cancelled": ("Task is cancelled; it will not restart automatically.", "none"),
    "reported_complete": ("The model reports completion; the outcome has not been independently verified.", "inspect_result"),
    "failed": ("Task failed.", "inspect_result"),
    "model_failed": ("Model request failed. Inspect the task before continuing.", "inspect_result"),
    "budget_exhausted": ("Execution budget exhausted; continuing does not reset the budget.", "inspect_result"),
    "no_tools": ("No permitted tools are available.", "configure_tools"),
    "context_limit": ("Task context exceeded the execution limit.", "inspect_result"),
    "repeated_action": ("Execution stopped to prevent a repeated action.", "inspect_result"),
    "invalid_completion": ("The completion claim lacked successful tool evidence.", "inspect_result"),
}


class TaskConversation:
    """Deterministic lifecycle controls over one selected durable run, never approvals."""

    def __init__(self, store, executor_factory, *, session="default", run_id=None):
        store.validate_session(session)
        if run_id is not None:
            store.validate_id(run_id)
        self.store, self.executor_factory, self.session = store, executor_factory, session
        self.initial_run_id = run_id
        self._candidate_revision = None

    def _response(self, intent, explanation, *, result=None, approval=False, preview=None, speech=None):
        return {"intent": intent, "confidence": 1.0, "source": "task_router", "task_mode": True,
                "task_session": self.session, "requires_approval": approval, "preview": preview,
                "result": result, "explanation": explanation, "speech_text": speech or explanation,
                "degradations": []}

    def _view(self, state):
        status = state["status"]
        message, next_action = _NEXT.get(status, ("Inspect this task before continuing.", "inspect_result"))
        verification = state.get("verification_report")
        projection = None
        if status == "reported_complete" and verification:
            verdict = verification.get("status")
            descriptions = {"passed": "All declared file conditions passed at the recorded check time.",
                            "partial": "Only some declared file conditions passed.",
                            "failed": "Declared file conditions failed verification.",
                            "unverifiable": "Declared file conditions could not be verified."}
            message = descriptions.get(verdict, "Inspect the declared file checks.")
            message += " This does not verify the entire goal; files may have changed since the check."
            projection = {key: verification.get(key) for key in ("status", "counts", "checked_at")}
        elif status == "reported_complete" and state.get("verification") == "pending_file_checks":
            message = "Declared file checks are pending or interrupted. Use executor verify to check without rerunning the task."
        observations = state.get("observations", [])
        token = state.get("approval_token")
        def text(value, limit=160):
            value = str(value or "")
            return (value.replace(token, "[redacted]") if token else value)[:limit]
        question = text(state.get("summary"), 1000) if status == "waiting_input" else None
        speech = message
        if question:
            message += " " + question
            speech += (" Review the question in the text view, then reply."
                       if observations or "context" in state or "acceptance" in state else " " + question)
        control = state.get("control_requested")
        if control and status not in {"cancelled", "reported_complete", "failed"}:
            notice = f" {control.title()} requested; a running call must return before acknowledgement."
            message += notice
            speech += notice
            if control == "cancel" and status != "needs_review":
                next_action = "wait_for_cancellation"
        successful = sum(o.get("status") == "success" for o in observations)
        failed = sum(o.get("status") in {"failed", "invalid_result", "interrupted", "denied", "unknown_tool"} for o in observations)
        view = {"run_id": state["run_id"], "status": status, "steps": state.get("steps", 0),
                "successful_observations": successful, "failed_observations": failed,
                "goal": text(state.get("goal")), "latest_action": text(observations[-1].get("action_summary")) if observations else "",
                "next_action": next_action, "question": question, "control_requested": control}
        if projection is not None:
            view["verification"] = projection
        preview = None
        if status == "waiting_approval" and control != "cancel" and state.get("pending_action"):
            action = state["pending_action"]
            preview = {"run_id": state["run_id"], "tool": action.get("tool"), "arguments": action.get("arguments")}
        return self._response("task_status", message, result={"task": view}, approval=status == "waiting_approval" and control != "cancel",
                              preview=preview, speech=f"{speech} {successful} successful tool results, {failed} failed results.")

    def _list(self, session, *, selection=False):
        rows = self.store.list()[:5]
        updated = self.store.update_task_session(self.session, session["revision"], run_id=session["run_id"],
                                       candidates=[row["run_id"] for row in rows])
        self._candidate_revision = updated["revision"]
        candidates = [{"number": n, "run_id": row["run_id"], "goal": str(row["goal"])[:160], "status": row["status"]}
                      for n, row in enumerate(rows, 1)]
        message = (f"Select a task by full ID or select task NUMBER @{self._candidate_revision}. "
                   "In this active conversation, the displayed number alone is also accepted."
                   if rows else "No tasks found. Use an explicit start task request.")
        return self._response("task_select_required" if selection else "task_list", message,
                              result={"candidates": candidates, "selection_revision": self._candidate_revision})

    def handle(self, text, *, approved=False):
        if approved:
            return self._response("task_error", "Generic approval is disabled in task mode. Use the exact text-token approval flow.")
        if not isinstance(text, str) or not text.strip() or len(text) > 4200:
            return self._response("task_error", "Task input must contain 1 to 4,200 characters.")
        try:
            return self._handle(text.strip())
        except (ValueError, RuntimeError, OSError, sqlite3.Error):
            return self._response("task_error", "Task request could not proceed. Check selection, model configuration, task/context state and whether another runner is active. No task was automatically restarted.")

    def _handle(self, text):
        session = self.store.task_session(self.session)
        if self.initial_run_id is not None:
            session = self.store.update_task_session(self.session, session["revision"],
                run_id=self.initial_run_id, candidates=[])
            self.initial_run_id = None
        normalized = text.casefold().rstrip(".!?。！？ ")
        control = next((key for key, terms in _CONTROLS.items() if normalized in terms), None)
        start = re.fullmatch(r"(?:start task|开始任务)(?:\s*[:：]\s*|\s+)(.+)", text, re.I | re.S)
        select = re.fullmatch(r"(?:select task|选择任务)\s+([0-9a-f]{32}|[1-5])(?:\s+@(\d{1,18}))?", normalized, re.I)
        if select is None and (self._candidate_revision is not None or session["candidates"]):
            select = re.fullmatch(r"([1-5])(?:\s+@(\d{1,18}))?", normalized)
        answer = re.fullmatch(r"(?:answer|回答)(?:\s*[:：]\s*|\s+)(.+)", text, re.I | re.S)
        if start:
            goal = start[1].strip()
            if not goal or len(goal) > 4000:
                raise ValueError("Invalid task goal.")
            executor = self.executor_factory()
            def bind(run_id):
                self.store.update_task_session(self.session, session["revision"], run_id=run_id, candidates=[])
                self._candidate_revision = None
            return self._view(executor.start(goal, on_created=bind))
        if select:
            key = select[1]
            if len(key) != 32:
                revision = int(select[2]) if select[2] else self._candidate_revision
                if revision is None:
                    return self._list(session, selection=True)
                if revision != session["revision"]:
                    raise ValueError("The displayed task list has changed.")
                index = int(key) - 1
                if index >= len(session["candidates"]):
                    return self._list(session, selection=True)
                key = session["candidates"][index]
            self.store.update_task_session(self.session, session["revision"], run_id=key, candidates=[])
            self._candidate_revision = None
            return self._view(self.store.get(key))
        if control == "list":
            return self._list(session)
        if not session["run_id"]:
            if control or answer:
                return self._list(session, selection=True)
            return self._response("task_clarify", "Use an explicit start task request, or select an existing task.")
        run_id = session["run_id"]
        state = self.store.get(run_id)
        if state.get("control_requested") == "cancel":
            self.store.request_task_control(run_id, "cancel")
            state = self.store.get(run_id)
        if control == "status":
            return self._view(state)
        if control in {"pause", "cancel"}:
            self.store.request_task_control(run_id, control)
            return self._view(self.store.get(run_id))
        if state["status"] in {"waiting_approval", "needs_review", "reported_complete", "failed", "cancelled", "repeated_action", "budget_exhausted"}:
            return self._view(state)
        if re.match(r"^(?:select task|选择任务|start task|开始任务|approve|批准)", normalized):
            return self._response("task_clarify", "Use an explicit task ID/number or a complete start task request. Approval requires the text-token flow.")
        if state["status"] == "waiting_input":
            if control == "resume":
                return self._view(state)
            return self._view(self.executor_factory().resume(run_id, answer=answer[1] if answer else text))
        if control == "resume":
            return self._view(self.executor_factory().resume(run_id))
        return self._response("task_clarify", "Task selected. Ask for progress, continue, pause or cancel; no execution was started.")
