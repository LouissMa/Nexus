from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import html
import json
import os
from pathlib import Path
import re
from time import monotonic
from uuid import uuid4

from .evaluation_cases import CASE_VERSION, execute_case, safe_path, select_cases
from .execution_metrics import estimate_cost, project_metrics, validate_pricing


_LIMIT = 1024 * 1024


def _now():
    return datetime.now(timezone.utc).isoformat()


def _identity(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"provider", "model", "tier"} or any(
        not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,200}", v) or "://" in v for v in value.values()
    ):
        raise ValueError("Model identity must contain only provider/model/tier labels.")
    return dict(value)


def _public_text(value, root):
    text = str(value or "").replace(str(root), "[evaluation]").replace(str(root).replace("\\", "/"), "[evaluation]")
    text = re.sub(r"https?://\S+|(?:[A-Za-z]:[\\/]|/)[^\s\"<>]*", "[path-or-url]", text)
    text = re.sub(r"(?i)\b(?:sk-[A-Za-z0-9_-]+|Bearer\s+\S+)", "[redacted]", text)
    return text[:4000]


def summarize_cases(cases):
    def ratio(values):
        passed = sum(v == "passed" for v in values)
        eligible = sum(v in {"passed", "failed"} for v in values)
        return {"passed": passed, "eligible": eligible, "rate": passed / eligible if eligible else None,
                "not_evaluable": sum(v == "not_evaluable" for v in values)}
    result = {}
    for kind in ("normal", "fault"):
        rows = [c for c in cases if c["kind"] == kind]
        result[kind + "_behavior"] = ratio([c["expected_behavior"]["status"] for c in rows])
        result[kind + "_behavior"]["skipped"] = sum(c["status"] in {"skipped", "not_started", "interrupted"} for c in rows)
    file_states = [c["file_condition_status"] for c in cases]
    applicable = [v for v in file_states if v != "not_applicable"]
    result["file_conditions"] = {"passed": applicable.count("passed"), "eligible": len(applicable),
        "rate": applicable.count("passed") / len(applicable) if applicable else None,
        "not_applicable": file_states.count("not_applicable"), "partial": applicable.count("partial"),
        "failed": applicable.count("failed"), "unverifiable": applicable.count("unverifiable")}
    result["model_reported_complete"] = sum(c["lifecycle_status"] == "reported_complete" for c in cases)
    result["human_assessment"] = {v: sum(c["human_assessment"] == v for c in cases) for v in ("passed", "partial", "failed", "not_reviewed")}
    return result


def render_report(report):
    def escaped(value):
        value = html.escape(str(value), quote=True)
        return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", value)
    lines = ["# Nexus evaluation", "", f"Mode: {escaped(report['mode'])}. Version: {escaped(report['case_version'])}.",
             "System behavior, file conditions and human assessments are separate; this is not a general success rate.", ""]
    for case in report["cases"]:
        lines += [f"## {escaped(case['case_id'])}", f"Status: {escaped(case['status'])}; lifecycle: {escaped(case['lifecycle_status'])}",
                  f"Behavior: {escaped(case['expected_behavior']['status'])}; files: {escaped(case['file_condition_status'])}; human: {escaped(case['human_assessment'])}",
                  escaped(case["summary"]), ""]
        metrics = case.get("metrics")
        if metrics:
            lines += ["Model attempts: " + escaped(metrics.get("model_attempts")),
                      "Tool dispatches: " + escaped(metrics.get("tool_dispatch_attempts")),
                      "Token coverage: " + escaped(metrics.get("usage", {}).get("coverage")),
                      "Estimated cost: " + escaped(case.get("cost", {}).get("amount")) + " (null means unavailable)", ""]
        for review in case["reviews"]:
            lines += [f"Human review ({escaped(review['verdict'])}): " + escaped(review["note"])]
    return "\n".join(lines) + "\n"


class EvaluationStore:
    def __init__(self, home):
        self.home = safe_path(home)

    def directory(self, key):
        if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{32}", key):
            raise ValueError("Invalid evaluation ID.")
        return safe_path(self.home / "evaluations" / key)

    def create(self, key):
        directory = self.directory(key)
        directory.parent.mkdir(parents=True, exist_ok=True)
        safe_path(directory.parent)
        directory.mkdir(exist_ok=False)
        return directory

    @contextmanager
    def locked(self, key):
        path = safe_path(self.directory(key) / ".evaluation.lock")
        with path.open("a+b") as handle:
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
                raise RuntimeError("Evaluation is busy.") from error
            try:
                yield
            finally:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def read(self, key):
        path = safe_path(self.directory(key) / "report.json")
        with path.open("rb") as source:
            payload = source.read(_LIMIT + 1)
        if len(payload) > _LIMIT:
            raise ValueError("Report exceeds 1 MiB.")
        try:
            report = json.loads(payload)
            valid = (isinstance(report, dict) and report.get("schema_version") == 1
                     and report.get("evaluation_id") == key and report.get("mode") in {"offline", "live"}
                     and isinstance(report.get("cases"), list) and len(report["cases"]) <= 24)
            if not valid:
                raise ValueError("Invalid report.")
            for case in report["cases"]:
                if (not isinstance(case, dict) or not isinstance(case.get("reviews"), list)
                        or not isinstance(case.get("summary"), str) or len(case["summary"]) > 4000
                        or case.get("kind") not in {"normal", "fault"}
                        or not isinstance(case.get("case_id"), str)
                        or not re.fullmatch(r"[a-z]+(?:-[a-z0-9]+)*", case["case_id"])
                        or case.get("human_assessment") not in {"passed", "partial", "failed", "not_reviewed"}
                        or case.get("file_condition_status") not in {"passed", "partial", "failed", "unverifiable", "not_applicable"}
                        or not isinstance(case.get("expected_behavior"), dict)
                        or case["expected_behavior"].get("status") not in {"passed", "failed", "not_evaluable"}
                        or "lifecycle_status" not in case or "status" not in case):
                    raise ValueError("Invalid case report.")
                for review in case["reviews"]:
                    if (not isinstance(review, dict) or review.get("verdict") not in {"passed", "partial", "failed"}
                            or not isinstance(review.get("note"), str) or not 1 <= len(review["note"]) <= 4000):
                        raise ValueError("Invalid human review.")
            return report
        except (TypeError, RecursionError, UnicodeError) as error:
            raise ValueError("Invalid report.") from error

    def save_locked(self, report):
        directory = self.directory(report["evaluation_id"])
        report["summary"] = summarize_cases(report["cases"])
        report["updated_at"] = _now()
        encoded = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
        markdown = render_report(report).encode("utf-8")
        if max(len(encoded), len(markdown)) > _LIMIT:
            raise ValueError("Report exceeds 1 MiB; previous report preserved.")
        # JSON is authoritative. Markdown is a disposable projection of that JSON.
        for name in ("report.json", "report.md"):
            safe_path(directory / name)
        for name, data in (("report.json", encoded), ("report.md", markdown)):
            target = safe_path(directory / name)
            temporary = safe_path(directory / (".report-" + uuid4().hex))
            try:
                with temporary.open("xb") as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
                safe_path(target)
                os.replace(temporary, target)
            finally:
                if temporary.exists() and not temporary.is_symlink():
                    temporary.unlink()

    def review(self, key, *, case_id, verdict, note):
        if verdict not in {"passed", "partial", "failed"} or not isinstance(note, str) or not note.strip() or len(note) > 4000:
            raise ValueError("Review requires a valid verdict and 1-4000 characters.")
        with self.locked(key):
            report = self.read(key)
            case = next((c for c in report["cases"] if c["case_id"] == case_id), None)
            if case is None:
                raise ValueError("Unknown case.")
            case["reviews"].append({"verdict": verdict, "note": note, "reviewed_at": _now()})
            case["human_assessment"] = verdict
            self.save_locked(report)
            return report


class EvaluationRunner:
    def __init__(self, home, *, model_factory=None, model_identity=None, clock=monotonic):
        self.store, self.model_factory = EvaluationStore(home), model_factory
        self.model_identity, self.clock = _identity(model_identity), clock

    def run(self, *, mode="offline", case_ids=None, max_calls=None, pricing=None):
        cases = select_cases(mode, case_ids)
        pricing = validate_pricing(pricing)
        if mode == "offline" and (max_calls is not None or pricing is not None or self.model_identity is not None):
            raise ValueError("Offline evaluation rejects live configuration.")
        if mode == "live" and (type(max_calls) is not int or not 1 <= max_calls <= 100 or self.model_factory is None or self.model_identity is None):
            raise ValueError("Live evaluation requires a model and explicit max-calls in 1-100.")
        if pricing and pricing["model"] != self.model_identity["model"]:
            raise ValueError("Pricing model does not match.")
        key = uuid4().hex
        directory = self.store.create(key)
        report = {"schema_version": 1, "evaluation_id": key, "case_version": CASE_VERSION, "mode": mode,
                  "status": "running", "created_at": _now(), "model": self.model_identity,
                  "pricing": pricing, "calls_reserved": 0, "budget": {"max_calls": max_calls, "suite_seconds": 300,
                  "case_seconds": 30, "case_steps": 8, "case_dispatches": 16}, "cases": []}
        for case in cases:
            report["cases"].append({"case_id": case["id"], "family": case["family"], "kind": case["kind"],
                "split": case["split"], "content_digest": case["content_digest"], "status": "not_started",
                "lifecycle_status": None, "file_condition_status": "not_applicable",
                "expected_behavior": {"status": "not_evaluable", "reason": "not_started"},
                "human_assessment": "not_reviewed", "reviews": [], "summary": "", "references": [], "metrics": None,
                "cost": {"status": "unavailable", "amount": None}})
        started = self.clock()
        with self.store.locked(key):
            self.store.save_locked(report)
            def reserve():
                if self.clock() - started >= 300 or (mode == "live" and report["calls_reserved"] >= max_calls):
                    return False
                if mode == "live":
                    report["calls_reserved"] += 1
                    self.store.save_locked(report)
                return True
            for case, row in zip(cases, report["cases"]):
                if self.clock() - started >= 300 or (mode == "live" and report["calls_reserved"] >= max_calls):
                    row.update(status="skipped", expected_behavior={"status": "not_evaluable", "reason": "budget_exhausted"})
                    continue
                before = self.clock()
                row["status"] = "running"
                self.store.save_locked(report)
                try:
                    result = execute_case(case, directory / case["id"], model_factory=self.model_factory if mode == "live" else None,
                                          before_model=reserve, clock=self.clock)
                    state = result["state"]
                    metrics = project_metrics(state)
                    row.update(status="needs_intervention" if state["status"] in {"waiting_approval", "waiting_input"} else "finished",
                        lifecycle_status=state["status"], file_condition_status=state.get("verification_report", {}).get("status", "not_applicable"),
                        expected_behavior=result["expected_behavior"], summary=_public_text(state.get("summary"), directory),
                        references=result["sources"][:50], metrics=metrics, case_wall_seconds=max(0, self.clock() - before))
                    if mode == "live" and metrics["usage"]["coverage"] == "complete":
                        costs = [estimate_cost(u, pricing, model=self.model_identity["model"]) for u in metrics["usage"]["calls"]]
                        if costs and all(c["status"] == "estimated" for c in costs):
                            row["cost"] = {"status": "estimated", "amount": format(sum(Decimal(c["amount"]) for c in costs), "f"), "currency": pricing["currency"]}
                    if mode == "live" and state["status"] == "cancelled":
                        row.update(status="interrupted", expected_behavior={"status": "not_evaluable", "reason": "interrupted"})
                        report["status"] = "interrupted"
                        self.store.save_locked(report)
                        return report
                except KeyboardInterrupt:
                    row.update(status="interrupted", expected_behavior={"status": "not_evaluable", "reason": "interrupted"})
                    report["status"] = "interrupted"
                    self.store.save_locked(report)
                    return report
                except Exception:
                    row.update(status="error", expected_behavior={"status": "not_evaluable", "reason": "infrastructure_error"})
                self.store.save_locked(report)
            report["status"] = "incomplete" if any(c["status"] in {"error", "skipped"} for c in report["cases"]) else "complete"
            self.store.save_locked(report)
        return report
