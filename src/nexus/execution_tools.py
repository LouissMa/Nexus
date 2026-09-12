from __future__ import annotations

import json
import hashlib
import math
import re
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Callable

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


@dataclass(frozen=True)
class ToolContract:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    side_effects: str = "none"
    idempotent: bool = False
    timeout_seconds: float | None = None


def _check_schema(schema: dict[str, Any]) -> None:
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if any(key in value for key in ("$ref", "$dynamicRef", "$recursiveRef")):
                raise ValueError("Tool schemas must be self-contained without references.")
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("Tool schemas must describe JSON objects.")
    visit(schema)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise ValueError("Invalid tool schema.") from error


class ToolRegistry:
    """Validate and dispatch one tool call; never plan or retry actions."""

    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolContract, Callable, Callable]] = {}
        self._bindings: dict[str, Callable] = {}

    def register(self, contract: ToolContract, handler: Callable, policy: Callable, *, binding=None) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", contract.name):
            raise ValueError("Invalid tool name.")
        if contract.name in self._tools:
            raise ValueError("Duplicate tool name.")
        if not contract.description.strip() or len(contract.description) > 1000:
            raise ValueError("A bounded description is required.")
        if contract.side_effects not in {"none", "local_write", "external"}:
            raise ValueError("Invalid side-effect declaration.")
        if type(contract.idempotent) is not bool:
            raise ValueError("Idempotence must be declared as a boolean.")
        if contract.timeout_seconds is not None and (
            isinstance(contract.timeout_seconds, bool)
            or not math.isfinite(contract.timeout_seconds)
            or contract.timeout_seconds <= 0
        ):
            raise ValueError("Timeout must be a positive finite number.")
        _check_schema(contract.input_schema)
        _check_schema(contract.output_schema)
        if contract.input_schema.get("additionalProperties") is not False:
            raise ValueError("Tool input schemas must reject unknown arguments.")
        self._tools[contract.name] = (deepcopy(contract), handler, policy)
        self._bindings[contract.name] = binding or (lambda: None)

    def binding(self, name: str, arguments: dict) -> str:
        entry = self._tools.get(name)
        definition = None if entry is None else [asdict(entry[0]), self._policy(entry[2]), self._bindings[name]()]
        payload = json.dumps([name, arguments, definition], sort_keys=True, allow_nan=False)
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _policy(callback: Callable) -> str:
        try:
            value = callback()
            return value if value in {"allow", "ask", "deny"} else "deny"
        except Exception:
            return "deny"

    def catalog(self) -> list[dict[str, Any]]:
        result = []
        for name, (contract, _, policy) in sorted(self._tools.items()):
            decision = self._policy(policy)
            if decision != "deny":
                result.append({**asdict(contract), "policy": decision,
                               "retry_policy": "never_automatic",
                               "timeout_enforcement": "adapter" if contract.timeout_seconds else "not_enforced"})
        return result

    def call(self, name: str, arguments: dict[str, Any], *, approved: bool = False) -> dict[str, Any]:
        result = {"tool": name, "status": "unknown_tool", "data": None, "effect_outcome": "not_started"}
        entry = self._tools.get(name)
        if entry is None:
            return result
        contract, handler, policy = entry
        try:
            payload = json.dumps(arguments, allow_nan=False).encode("utf-8")
            if len(payload) > 16384:
                raise ValueError("Input limit exceeded.")
            Draft202012Validator(contract.input_schema).validate(arguments)
            arguments = json.loads(payload)
        except (TypeError, ValueError, ValidationError, RecursionError):
            return {**result, "status": "invalid_arguments"}
        decision = self._policy(policy)
        if decision == "deny":
            return {**result, "status": "denied"}
        if decision == "ask" and approved is not True:
            return {**result, "status": "approval_required"}
        result["effect_outcome"] = "none" if contract.side_effects == "none" else "unknown"
        try:
            data = handler(arguments, approved is True)
        except Exception:
            return {**result, "status": "failed"}
        try:
            payload = json.dumps(data, allow_nan=False).encode("utf-8")
            if len(payload) > 65536:
                return {**result, "status": "result_too_large"}
            Draft202012Validator(contract.output_schema).validate(data)
        except (TypeError, ValueError, ValidationError, RecursionError):
            return {**result, "status": "invalid_result"}
        return {**result, "status": "success", "data": json.loads(payload),
                "effect_outcome": "none" if contract.side_effects == "none" else "adapter_reported_success"}


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def build_tool_registry(*, tools: Any = None, automations: Any = None) -> ToolRegistry:
    if tools is None or automations is None:
        from nexus.automation import AutomationManager, load_automation_settings
        from nexus.config import load_tool_settings, nexus_home
        from nexus.integrations.manager import build_tool_manager
        from nexus.store import JsonStore

        home = nexus_home()
        if tools is None:
            tools = build_tool_manager(load_tool_settings(), home)
        if automations is None:
            automations = AutomationManager(load_automation_settings(), home, JsonStore.from_env(), tool_manager=tools)
    registry = ToolRegistry()
    path = {"type": "string", "minLength": 1, "maxLength": 2000}
    schemas = {
        "list": _object({"path": path}, ["path"]),
        "read": _object({"path": path, "max_bytes": {"type": "integer", "minimum": 1, "maximum": 16000}}, ["path"]),
        "search": _object({"path": path, "query": {"type": "string", "minLength": 1, "maxLength": 200},
                           "mode": {"enum": ["filename", "content"]}}, ["path", "query"]),
    }
    output_fields = {"list": "entries", "read": "content", "search": None}
    for operation, schema in schemas.items():
        def policy(op=operation):
            settings = tools.settings.get("filesystem", {})
            return "allow" if settings.get("enabled") and op in settings.get("allowed_operations", []) else "deny"

        def run(arguments, approved, op=operation):
            if op == "read":
                arguments.setdefault("max_bytes", 16000)
            return tools.execute("filesystem", op, **arguments).data

        field = output_fields[operation]
        output = {"type": "object"}
        if field:
            output.update({"required": [field], "properties": {field: {"type": "string" if operation == "read" else "array"}}})
        else:
            output["required"] = ["matches"]
            output["properties"] = {"matches": {"type": "array"}}
        registry.register(ToolContract(f"filesystem.{operation}", f"{operation.title()} within authorized filesystem roots.",
                                       schema, output, idempotent=True), run, policy,
                          binding=lambda: tools.settings.get("filesystem", {}))
    for alias, definition in automations.settings.items():
        def policy(key=alias):
            current = automations.settings.get(key, {})
            return current.get("policy", "deny") if current.get("enabled") else "deny"

        def run(arguments, approved, key=alias):
            return automations.run(key, approved=approved)

        kind = definition["type"]
        effect = "none" if kind == "github_inspect" else "local_write" if kind == "status_report" else "external"
        registry.register(ToolContract(
            f"automation.{alias}", f"Run the registered {kind} automation '{alias}'.",
            _object({}, []), {"type": "object", "required": ["status"], "properties": {"status": {"const": "success"}}},
            side_effects=effect, idempotent=effect == "none",
            timeout_seconds=definition.get("timeout_seconds") if kind == "command" else None,
        ), run, policy, binding=lambda key=alias: automations.settings.get(key, {}))
    return registry
