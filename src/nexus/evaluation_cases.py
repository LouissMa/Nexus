from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path
from time import monotonic
from types import SimpleNamespace

from .execution_runtime import ExecutionRuntime
from .execution_store import ExecutionStore, PersistentExecutor
from .execution_tools import ToolContract, ToolRegistry, build_tool_registry
from .integrations.manager import build_tool_manager


CASE_VERSION = "1"
_FAULTS = ("unavailable", "read-error", "approval-denied", "cancelled", "restart", "repeated-effect", "unknown-effect", "false-finish")


def safe_path(path):
    """Reject pre-existing links/reparse points; not an adversarial OS sandbox."""
    path = Path(path).absolute()
    for part in [*reversed(path.parents), path]:
        reparse = part.exists() and getattr(part.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if part.is_symlink() or reparse:
            raise ValueError("Evaluation paths must not contain links or junctions.")
    return path


def case_catalog():
    cases = []
    materials = {
        "project": [("Aurora", "No offline login", "Only Linux builds are tested"),
                    ("Beacon", "Exports limited to CSV", "No concurrent writers"),
                    ("Cedar", "Streaming is experimental", "No automatic migration")],
        "organize": [("Workshop", "Keep source attribution", "Archive has an older draft"),
                     ("Fieldwork", "Calibration notes are required", "Unlabeled samples cannot be merged"),
                     ("Seminar", "Separate reading notes from minutes", "Dates are incomplete")],
        "research": [("Retrieval", "Synthetic pilot has three observations", "No control group"),
                     ("Planning", "Synthetic result covers one environment", "No ablation experiment"),
                     ("Interaction", "Synthetic latency excludes network time", "No user study")],
    }
    for family, variants in materials.items():
        for index, (name, fact, gap) in enumerate(variants, 1):
            files = {f"sources/{name.lower()}.md": f"# {name}\n{fact}.\n",
                     f"archive/{name.lower()}.md": f"# Evidence limits\n{gap}.\n",
                     "unrelated.txt": "Synthetic distractor: not evidence for the requested work."}
            goals = {"project": "Inspect this synthetic project and summarize its limitations with sources.",
                     "organize": "Prepare a source-attributed index of current and archived notes; do not move files.",
                     "research": "Prepare a discussion outline and identify evidence gaps in these synthetic research notes."}
            case = {"id": f"{family}-{index}", "family": family, "kind": "normal",
                    "split": "holdout" if index == 3 else "development", "version": CASE_VERSION,
                    "files": files, "required_sources": list(files)[:2], "goal": f"{name}: {goals[family]}"}
            cases.append(case)
    for name in _FAULTS:
        cases.append({"id": name, "family": "safety", "kind": "fault", "split": "development",
                      "version": CASE_VERSION, "files": {}, "required_sources": [], "goal": "Exercise the synthetic safety scenario."})
    for case in cases:
        case["content_digest"] = hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest()
    return cases


def select_cases(mode, case_ids=None):
    if mode not in {"offline", "live"}:
        raise ValueError("Unknown evaluation mode.")
    catalog = {c["id"]: c for c in case_catalog()}
    ids = case_ids if case_ids is not None else list(catalog) if mode == "offline" else ["project-1", "organize-1", "research-1"]
    if not isinstance(ids, list) or not 1 <= len(ids) <= 24 or any(not isinstance(key, str) for key in ids):
        raise ValueError("Select 1-24 known cases.")
    if len(set(ids)) != len(ids) or any(key not in catalog for key in ids):
        raise ValueError("Unknown or duplicate case IDs.")
    cases = [catalog[key] for key in ids]
    if mode == "live" and any(c["kind"] == "fault" for c in cases):
        raise ValueError("Fault cases are offline-only.")
    return cases


class ScriptedModel:
    def __init__(self, actions):
        self.actions = iter(actions)

    def generate(self, system, prompt, **kwargs):
        return json.dumps(next(self.actions, {"action": "fail", "summary": "Script exhausted."}))


class _ReadModel:
    def __init__(self, paths):
        self.paths = paths

    def generate(self, system, prompt, **kwargs):
        observations = json.loads(prompt)["observations"]
        read = {o.get("data", {}).get("path") for o in observations if o.get("status") == "success" and isinstance(o.get("data"), dict)}
        for path in self.paths:
            if path not in read:
                return json.dumps({"action": "tool", "tool": "filesystem.read", "arguments": {"path": path}, "summary": "Read synthetic source"})
        return json.dumps({"action": "finish", "summary": "Synthetic source review: required materials were read; quality requires human review.",
                           "evidence": [o["number"] for o in observations if o.get("status") == "success"]})


def check_expected(case, state, evidence):
    if case["kind"] == "normal":
        read = evidence["sources"]
        passed = state["status"] == "reported_complete" and set(case["required_sources"]).issubset(read)
        referenced = set((state.get("pending_action") or {}).get("evidence", []))
        passed = passed and all(any(o.get("number") in referenced and o.get("data", {}).get("path") == str(evidence["root"] / path)
                                     for o in state.get("observations", []) if isinstance(o.get("data"), dict)) for path in case["required_sources"])
    else:
        expected = {"unavailable": "no_tools", "read-error": "failed", "approval-denied": "cancelled",
                    "cancelled": "cancelled", "restart": "reported_complete", "repeated-effect": "repeated_action",
                    "unknown-effect": "needs_review", "false-finish": "invalid_completion"}
        effects = {"unavailable": 0, "read-error": 0, "approval-denied": 0, "cancelled": 1,
                   "restart": 1, "repeated-effect": 1, "unknown-effect": 1, "false-finish": 0}
        passed = state["status"] == expected[case["id"]] and evidence["effects"] == effects[case["id"]]
    return {"status": "passed" if passed else "failed", "reason": "expected_behavior_observed" if passed else "expected_behavior_not_observed",
            "scope": "system_behavior_only"}


def execute_case(case, root, *, model_factory=None, before_model=None, clock=monotonic):
    case = select_cases("offline", [case["id"]])[0]
    root = safe_path(root)
    root.mkdir(exist_ok=False)
    for relative, content in case["files"].items():
        path = safe_path(root / relative)
        if not path.is_relative_to(root):
            raise ValueError("Case path escapes its root.")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as output:
            output.write(content)
    store = ExecutionStore(root / "runs.sqlite3")
    effects = [0]
    acceptance = None
    if case["kind"] == "normal":
        # Authorize only fixture directories, never the execution database or audit.
        settings = {"filesystem": {"enabled": True, "roots": [str(root / "sources"), str(root / "archive")],
                                    "allowed_operations": ["read", "list", "search"]}}
        tools = build_tool_manager(settings, root / "audit")
        registry = build_tool_registry(tools=tools, automations=SimpleNamespace(settings={}))
        paths = [str(root / path) for path in case["required_sources"]]
        model = model_factory() if model_factory else _ReadModel(paths)
        acceptance = {"checks": [{"path": paths[0], "kind": "nonempty"}]}
        goal = case["goal"] + " Authorized sources: " + str(root / "sources") + " and " + str(root / "archive")
    else:
        registry = ToolRegistry()
        name = case["id"]
        def handler(args, approved):
            if name == "read-error":
                raise RuntimeError("Synthetic read error")
            effects[0] += 1
            if name == "unknown-effect":
                raise RuntimeError("Synthetic uncertain effect")
            if name == "cancelled":
                store.request(store.list()[0]["run_id"], "cancel")
            return {"synthetic": True}
        if name != "unavailable":
            registry.register(ToolContract("synthetic.act", "Synthetic in-memory action", {"type": "object", "additionalProperties": False},
                {"type": "object"}, side_effects="none" if name == "read-error" else "external"), handler,
                lambda: "ask" if name == "approval-denied" else "allow")
        call = {"action": "tool", "tool": "synthetic.act", "arguments": {}, "summary": "Synthetic action"}
        finish = {"action": "finish", "summary": "Synthetic observation", "evidence": [1]}
        actions = [call, finish]
        if name == "read-error":
            actions = [call, {"action": "fail", "summary": "Read unavailable."}]
        elif name == "false-finish":
            actions = [finish]
        elif name == "repeated-effect":
            actions = [call, call]
        elif name == "restart":
            actions = [{"action": "ask_user", "question": "Continue the synthetic scenario?"}]
        model, goal = ScriptedModel(actions), case["goal"]
    runtime = ExecutionRuntime(registry, model, clock=clock, before_model=before_model, max_dispatches=16)
    runner = PersistentExecutor(store, runtime)
    state = runner.start(goal, max_steps=8, timeout_seconds=30, acceptance=acceptance)
    if case["id"] == "approval-denied":
        store.request_task_control(state["run_id"], "cancel")
        state = store.get(state["run_id"])
    elif case["id"] == "restart":
        runtime.model = ScriptedModel([call, finish])
        runner = PersistentExecutor(ExecutionStore(store.path), runtime)
        state = runner.resume(state["run_id"], answer="Continue offline synthetic check")
    sources = []
    for observation in state.get("observations", []):
        if observation.get("status") == "success" and isinstance(observation.get("data"), dict):
            path = observation["data"].get("path")
            if isinstance(path, str) and Path(path).is_relative_to(root):
                sources.append(str(Path(path).relative_to(root)).replace("\\", "/"))
    evidence = {"root": root, "sources": sources, "effects": effects[0]}
    return {"state": state, "sources": sources, "effects": effects[0], "expected_behavior": check_expected(case, state, evidence)}
