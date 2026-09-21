from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal
import re


def normalize_usage(raw):
    result = {"status": "unavailable", "input_tokens": None, "output_tokens": None,
              "total_tokens": None, "billing_supported": False}
    if raw is None:
        return result
    if not isinstance(raw, dict):
        return {**result, "status": "invalid"}
    names = {"prompt_tokens": "input_tokens", "completion_tokens": "output_tokens", "total_tokens": "total_tokens"}
    for source, target in names.items():
        if source in raw:
            value = raw[source]
            if type(value) is not int or not 0 <= value <= 2**63 - 1:
                return {**result, "status": "invalid"}
            result[target] = value
    counts = [result[key] for key in ("input_tokens", "output_tokens", "total_tokens")]
    if all(value is not None for value in counts) and counts[0] + counts[1] != counts[2]:
        return {**result, "status": "invalid"}
    supported = not (set(raw) - set(names) - {"prompt_tokens_details", "completion_tokens_details"})
    for name in ("prompt_tokens_details", "completion_tokens_details"):
        if name in raw:
            detail = raw[name]
            if not isinstance(detail, dict) or any(type(v) is not int or not 0 <= v <= 2**63 - 1 for v in detail.values()):
                return {**result, "status": "invalid"}
            known = {"cached_tokens", "audio_tokens", "reasoning_tokens", "accepted_prediction_tokens", "rejected_prediction_tokens"}
            supported = supported and not (set(detail) - known) and all(v == 0 for v in detail.values())
    result["status"] = "available" if any(v is not None for v in counts) else "unavailable"
    result["billing_supported"] = bool(supported)
    return result


def validate_pricing(pricing):
    if pricing is None:
        return None
    fields = {"model", "currency", "effective_date", "input_per_million", "output_per_million"}
    if not isinstance(pricing, dict) or set(pricing) != fields:
        raise ValueError("Invalid pricing fields.")
    if not isinstance(pricing["model"], str) or not 1 <= len(pricing["model"]) <= 200:
        raise ValueError("Invalid pricing model.")
    if not isinstance(pricing["currency"], str) or not re.fullmatch(r"[A-Z]{3}", pricing["currency"]):
        raise ValueError("Invalid currency.")
    if not isinstance(pricing["effective_date"], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", pricing["effective_date"]):
        raise ValueError("Invalid pricing date.")
    date.fromisoformat(pricing["effective_date"])
    for key in ("input_per_million", "output_per_million"):
        value = pricing[key]
        if not isinstance(value, str) or not re.fullmatch(r"\d{1,12}(?:\.\d{1,12})?", value):
            raise ValueError("Prices must be bounded nonnegative decimal strings.")
    return dict(pricing)


def estimate_cost(usage, pricing, *, model):
    pricing = validate_pricing(pricing)
    result = {"status": "unavailable", "amount": None, "currency": pricing["currency"] if pricing else None}
    if pricing is None or pricing["model"] != model or usage.get("status") != "available" or not usage.get("billing_supported"):
        return result
    inputs, outputs = usage.get("input_tokens"), usage.get("output_tokens")
    if type(inputs) is not int or type(outputs) is not int:
        return result
    amount = (Decimal(inputs) * Decimal(pricing["input_per_million"])
              + Decimal(outputs) * Decimal(pricing["output_per_million"])) / Decimal(1000000)
    return {**result, "status": "estimated", "amount": format(amount, "f")}


def new_metrics(*, coverage="complete"):
    return {"schema_version": 1, "coverage": coverage, "attempts": [], "approval_stops": 0, "clarification_stops": 0}


def begin_attempt(metrics, kind):
    if kind not in {"model", "tool"} or len(metrics["attempts"]) >= 200:
        raise ValueError("Invalid or exhausted attempt ledger.")
    key = str(len(metrics["attempts"]) + 1)
    metrics["attempts"].append({"id": key, "kind": kind, "status": "pending"})
    return key


def finish_attempt(metrics, attempt_id, status, *, usage=None):
    if usage is not None:
        allowed = {"status", "input_tokens", "output_tokens", "total_tokens", "billing_supported"}
        if (not isinstance(usage, dict) or set(usage) != allowed
                or usage.get("status") not in {"available", "unavailable", "invalid"}
                or type(usage.get("billing_supported")) is not bool
                or any(v is not None and (type(v) is not int or not 0 <= v <= 2**63 - 1)
                       for v in (usage.get("input_tokens"), usage.get("output_tokens"), usage.get("total_tokens")))):
            usage = {**normalize_usage(None), "status": "invalid"}
    entry = next(e for e in metrics["attempts"] if e["id"] == attempt_id)
    if entry["status"] != "pending":
        if entry["status"] == status and entry.get("usage") == usage:
            return
        raise ValueError("Attempt already completed.")
    entry["status"] = status
    if usage is not None:
        entry["usage"] = dict(usage)


def recover_pending(metrics):
    for entry in metrics["attempts"]:
        if entry["status"] == "pending":
            entry["status"] = "unknown"


def project_metrics(state):
    metrics = state.get("metrics")
    if metrics is None:
        return {"coverage": "legacy_unavailable"}
    models = [e for e in metrics["attempts"] if e["kind"] == "model"]
    tools = [e for e in metrics["attempts"] if e["kind"] == "tool"]
    usages = [e.get("usage", normalize_usage(None)) for e in models]
    covered = [u for u in usages if u.get("status") == "available" and u.get("input_tokens") is not None and u.get("output_tokens") is not None]
    complete = bool(models) and len(covered) == len(models) and metrics["coverage"] == "complete"
    usage = {"coverage": "complete" if complete else "partial" if covered else "unavailable",
             "covered_calls": len(covered), "attempted_calls": len(models), "calls": usages}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        values = [u.get(key) for u in usages]
        usage[key] = sum(values) if complete and all(type(v) is int for v in values) else None
    return {"coverage": metrics["coverage"], "model_attempts": len(models),
            "model_responses": sum(e["status"] == "response" for e in models),
            "model_errors": sum(e["status"] == "error" for e in models),
            "model_unknown": sum(e["status"] in {"unknown", "pending"} for e in models),
            "tool_dispatch_attempts": len(tools), "tool_outcomes": dict(Counter(e["status"] for e in tools)),
            "approval_stops": metrics["approval_stops"], "clarification_stops": metrics["clarification_stops"],
            "elapsed_active_seconds": state.get("elapsed_seconds", 0),
            "verification_seconds": state.get("verification_total_seconds", sum(r.get("duration_seconds", 0) for r in
                [*state.get("verification_history", []), state.get("verification_report", {})])),
            "usage": usage}
