from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic


_TYPES = {"string", "integer", "number", "boolean", "object", "array", "null"}


def validate_acceptance(value):
    """Return an isolated bounded contract, never model-authored executable checks."""
    try:
        payload = json.dumps(value, allow_nan=False).encode("utf-8")
        if len(payload) > 16384:
            raise ValueError("Acceptance exceeds 16 KiB.")
        value = json.loads(payload)
    except (TypeError, RecursionError, OverflowError) as error:
        raise ValueError("Invalid acceptance contract.") from error
    if not isinstance(value, dict) or set(value) != {"checks"}:
        raise ValueError("Acceptance requires only checks.")
    checks = value["checks"]
    if not isinstance(checks, list) or not 1 <= len(checks) <= 20:
        raise ValueError("Acceptance requires 1-20 checks.")
    for check in checks:
        if not isinstance(check, dict):
            raise ValueError("Invalid acceptance check.")
        kind, path = check.get("kind"), check.get("path")
        if not isinstance(kind, str) or kind not in {"exists", "nonempty", "contains", "json_fields"}:
            raise ValueError("Unknown acceptance check kind.")
        fields = {"path", "kind"} | ({"value"} if kind == "contains" else {"fields"} if kind == "json_fields" else set())
        if set(check) != fields:
            raise ValueError("Unexpected acceptance check fields.")
        if not isinstance(path, str) or not 1 <= len(path) <= 2000 or "\x00" in path or not Path(path).is_absolute():
            raise ValueError("Acceptance paths must be bounded absolute paths.")
        if kind == "contains" and (not isinstance(check["value"], str) or not 1 <= len(check["value"]) <= 1000):
            raise ValueError("Expected text must contain 1-1000 characters.")
        if kind == "json_fields":
            types = check["fields"]
            if not isinstance(types, dict) or not 1 <= len(types) <= 30 or any(
                not 1 <= len(key) <= 100 or not isinstance(expected, str) or expected not in _TYPES
                for key, expected in types.items()
            ):
                raise ValueError("JSON fields require 1-30 bounded names and supported types.")
    return value


def _matches_type(value, expected):
    if expected == "number":
        return type(value) in {int, float} and (type(value) is int or math.isfinite(value))
    return type(value) is {"string": str, "integer": int, "boolean": bool,
                           "object": dict, "array": list, "null": type(None)}[expected]


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key.")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-finite JSON constant.")


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("JSON number exceeds the supported finite range.")
    return result


class FileVerifier:
    """Read-only, time-specific checks through existing tool permissions."""

    def __init__(self, registry, *, clock=monotonic):
        self.registry, self.clock = registry, clock

    def verify(self, acceptance):
        contract = validate_acceptance(acceptance)
        started = self.clock()
        results = []
        for number, check in enumerate(contract["checks"], 1):
            item = {"number": number, "path": check["path"], "kind": check["kind"],
                    "status": "unverifiable", "reason": "budget_exhausted"}
            if self.clock() - started < 5:
                try:
                    result = self.registry.call("filesystem.read", {"path": check["path"], "max_bytes": 16000})
                    item.update(self._check(check, result))
                except Exception:
                    item["reason"] = "read_unavailable"
            results.append(item)
        counts = {status: sum(item["status"] == status for item in results)
                  for status in ("passed", "failed", "unverifiable")}
        status = ("passed" if counts["passed"] == len(results) else "partial" if counts["passed"]
                  else "failed" if counts["failed"] else "unverifiable")
        return {"status": status, "scope": "declared_file_conditions_only",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": max(0, self.clock() - started), "counts": counts, "checks": results}

    @staticmethod
    def _check(check, result):
        unavailable = {"status": "unverifiable", "reason": "read_unavailable"}
        if result.get("status") != "success":
            return unavailable
        data = result.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("content"), str) or type(data.get("truncated")) is not bool:
            return {**unavailable, "reason": "invalid_read_result"}
        if data["truncated"]:
            return {**unavailable, "reason": "truncated"}
        content, kind = data["content"], check["kind"]
        if kind in {"contains", "json_fields"} and "\ufffd" in content:
            return {**unavailable, "reason": "text_decoding_uncertain"}
        if kind == "exists":
            passed = True
        elif kind == "nonempty":
            passed = bool(content)
        elif kind == "contains":
            passed = check["value"] in content
        else:
            try:
                value = json.loads(content, object_pairs_hook=_unique_object,
                                   parse_constant=_reject_constant, parse_float=_finite_float)
                passed = isinstance(value, dict) and all(
                    name in value and _matches_type(value[name], expected) for name, expected in check["fields"].items())
            except (ValueError, RecursionError):
                passed = False
        return {"status": "passed" if passed else "failed",
                "reason": "condition_met" if passed else "condition_not_met"}
