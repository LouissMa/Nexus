from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any


PRIVACY_SCOPES = ("private", "personal", "shared")
MEMORY_STATUSES = ("active", "archived", "forgotten")
IMPORTANCE_SOURCES = ("automatic", "user")
_PRIVACY_RANK = {scope: index for index, scope in enumerate(PRIVACY_SCOPES)}
_WORD_PATTERN = re.compile(r"[a-z0-9\u4e00-\u9fff]+")
_HIGH_SIGNAL_TAGS = {
    "deadline",
    "exam",
    "family",
    "goal",
    "health",
    "identity",
    "important",
    "milestone",
    "preference",
    "relationship",
}
_HIGH_SIGNAL_TERMS = {
    "always",
    "deadline",
    "important",
    "must",
    "never",
    "prefer",
    "remember",
    "tomorrow",
    "重要",
    "截止",
    "目标",
    "考试",
    "家人",
    "喜欢",
}


class MemoryLifecycleError(ValueError):
    """Raised when a memory lifecycle value or transition is invalid."""


@dataclass(frozen=True)
class DuplicateMatch:
    kind: str
    memory_id: str | None = None
    similarity: float = 0.0


@dataclass(frozen=True)
class CompressionGroup:
    group_key: str
    source_ids: list[str]
    summary_text: str
    tags: list[str]
    privacy: str
    expires_at: str | None


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(microsecond=0).isoformat()


def parse_memory_time(value: str | None, field_name: str) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise MemoryLifecycleError(
            f"{field_name} must be a valid ISO timestamp."
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def validate_importance(value: float | int | str) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise MemoryLifecycleError(
            "importance must be a number from 0.0 to 1.0."
        ) from exc
    if not 0.0 <= score <= 1.0:
        raise MemoryLifecycleError("importance must be between 0.0 and 1.0.")
    return round(score, 3)


def score_importance(text: str, tags: list[str]) -> float:
    normalized_tags = {tag.strip().lower() for tag in tags if tag.strip()}
    normalized_content = text.lower()
    score = 0.25
    score += min(len(text.strip()) / 500.0, 0.15)
    score += min(len(normalized_tags) * 0.025, 0.1)
    score += min(len(normalized_tags & _HIGH_SIGNAL_TAGS) * 0.08, 0.24)
    score += min(
        sum(term in normalized_content for term in _HIGH_SIGNAL_TERMS) * 0.06, 0.18
    )
    return round(max(0.1, min(score, 0.9)), 3)


def normalize_memory(
    memory: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    normalized = dict(memory)
    text = str(normalized.get("text", "")).strip()
    tags = [str(tag).strip() for tag in normalized.get("tags", []) if str(tag).strip()]
    if not normalized.get("id"):
        raise MemoryLifecycleError("memory id is required.")
    if not text:
        raise MemoryLifecycleError("memory text is required.")

    privacy = str(normalized.get("privacy", "private"))
    if privacy not in PRIVACY_SCOPES:
        raise MemoryLifecycleError(
            f"privacy must be one of: {', '.join(PRIVACY_SCOPES)}."
        )
    status = str(normalized.get("status", "active"))
    if status not in MEMORY_STATUSES:
        raise MemoryLifecycleError(
            f"status must be one of: {', '.join(MEMORY_STATUSES)}."
        )

    has_importance = "importance" in normalized
    importance = (
        validate_importance(normalized["importance"])
        if has_importance
        else score_importance(text, tags)
    )
    source = str(
        normalized.get("importance_source", "user" if has_importance else "automatic")
    )
    if source not in IMPORTANCE_SOURCES:
        raise MemoryLifecycleError(
            f"importance_source must be one of: {', '.join(IMPORTANCE_SOURCES)}."
        )

    created_at = parse_memory_time(normalized.get("created_at"), "created_at")
    if created_at is None:
        created_at = now or datetime.now(UTC)
    updated_at = (
        parse_memory_time(normalized.get("updated_at"), "updated_at") or created_at
    )
    expires_at = parse_memory_time(normalized.get("expires_at"), "expires_at")

    normalized.update(
        {
            "text": text,
            "tags": tags,
            "created_at": utc_iso(created_at),
            "updated_at": utc_iso(updated_at),
            "importance": importance,
            "importance_source": source,
            "pinned": bool(normalized.get("pinned", False)),
            "privacy": privacy,
            "status": status,
            "expires_at": utc_iso(expires_at) if expires_at else None,
            "duplicate_of": normalized.get("duplicate_of"),
            "supersedes": normalized.get("supersedes"),
            "conflicts_with": list(dict.fromkeys(normalized.get("conflicts_with", []))),
            "summary_of": list(dict.fromkeys(normalized.get("summary_of", []))),
            "archived_at": normalized.get("archived_at"),
            "forgotten_at": normalized.get("forgotten_at"),
        }
    )
    return normalized


def normalized_text(text: str) -> str:
    return " ".join(_WORD_PATTERN.findall(text.lower()))


def detect_duplicate(
    memories: list[dict[str, Any]],
    text: str,
    tags: list[str] | None = None,
    *,
    near_threshold: float = 0.75,
) -> DuplicateMatch:
    del tags
    candidate = normalized_text(text)
    best = DuplicateMatch("none")
    for memory in memories:
        if memory.get("status", "active") == "forgotten":
            continue
        existing = normalized_text(str(memory.get("text", "")))
        if not existing:
            continue
        if candidate == existing:
            return DuplicateMatch("exact", str(memory["id"]), 1.0)
        similarity = SequenceMatcher(None, candidate, existing).ratio()
        candidate_terms = set(candidate.split())
        existing_terms = set(existing.split())
        overlap = (
            len(candidate_terms & existing_terms)
            / len(candidate_terms | existing_terms)
            if candidate_terms and existing_terms
            else 0.0
        )
        similarity = max(similarity, overlap)
        if similarity >= near_threshold and similarity > best.similarity:
            best = DuplicateMatch("near", str(memory["id"]), round(similarity, 6))
    return best


def effective_importance(memory: dict[str, Any]) -> float:
    if memory.get("pinned"):
        return 1.0
    return validate_importance(memory.get("importance", 0.5))


def is_memory_eligible(
    memory: dict[str, Any],
    *,
    privacy: str = "private",
    include_archived: bool = False,
    now: datetime | None = None,
) -> bool:
    if privacy not in PRIVACY_SCOPES:
        raise MemoryLifecycleError(
            f"privacy must be one of: {', '.join(PRIVACY_SCOPES)}."
        )
    normalized = normalize_memory(memory, now=now)
    status = normalized["status"]
    if status == "forgotten":
        return False
    if status == "archived" and not include_archived:
        return False
    if _PRIVACY_RANK[normalized["privacy"]] < _PRIVACY_RANK[privacy]:
        return False
    expires_at = parse_memory_time(normalized.get("expires_at"), "expires_at")
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    if (
        expires_at
        and expires_at <= current.astimezone(UTC)
        and not normalized["pinned"]
    ):
        return False
    return True


def apply_transition(
    memory: dict[str, Any],
    transition: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    normalized = normalize_memory(memory, now=current)
    if normalized["status"] == "forgotten" and transition != "restore":
        raise MemoryLifecycleError(
            "A forgotten memory must be restored before another transition."
        )
    timestamp = utc_iso(current)
    if transition == "archive":
        normalized["status"] = "archived"
        normalized["archived_at"] = timestamp
        normalized["forgotten_at"] = None
    elif transition == "forget":
        normalized["status"] = "forgotten"
        normalized["forgotten_at"] = timestamp
    elif transition == "restore":
        normalized["status"] = "active"
        normalized["archived_at"] = None
        normalized["forgotten_at"] = None
    else:
        raise MemoryLifecycleError(
            "transition must be one of: archive, forget, restore."
        )
    normalized["updated_at"] = timestamp
    return normalized


def build_compression_plan(
    memories: list[dict[str, Any]],
    *,
    older_than_days: int,
    max_importance: float,
    now: datetime | None = None,
    minimum_group_size: int = 2,
) -> list[CompressionGroup]:
    if older_than_days < 0:
        raise MemoryLifecycleError("older_than_days must be zero or greater.")
    threshold = validate_importance(max_importance)
    if minimum_group_size < 2:
        raise MemoryLifecycleError("minimum_group_size must be at least 2.")
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    cutoff = current.astimezone(UTC) - timedelta(days=older_than_days)
    groups: dict[str, list[dict[str, Any]]] = {}
    already_summarized = {
        source_id
        for item in memories
        for source_id in item.get("summary_of", [])
        if item.get("status", "active") != "forgotten"
    }

    for raw in memories:
        item = normalize_memory(raw, now=current)
        created = parse_memory_time(item["created_at"], "created_at")
        if (
            item["status"] != "active"
            or item["pinned"]
            or item["importance"] > threshold
            or created is None
            or created > cutoff
            or item["id"] in already_summarized
            or item.get("summary_of")
        ):
            continue
        primary_tag = item["tags"][0].lower() if item["tags"] else "untagged"
        key = f"{created:%Y-%m}:{primary_tag}:{item['privacy']}"
        groups.setdefault(key, []).append(item)

    plans: list[CompressionGroup] = []
    for key, items in sorted(groups.items()):
        if len(items) < minimum_group_size:
            continue
        items.sort(key=lambda item: (item["created_at"], item["id"]))
        source_ids = [str(item["id"]) for item in items]
        highlights: list[str] = []
        for item in items[:8]:
            compact = re.sub(r"\s+", " ", str(item["text"])).strip()
            if len(compact) > 160:
                compact = f"{compact[:157]}..."
            highlights.append(compact)
        if len(items) > len(highlights):
            highlights.append(f"... and {len(items) - len(highlights)} more items")
        details = "; ".join(highlights)
        tags = sorted({tag for item in items for tag in item["tags"]})
        expiries = [
            parse_memory_time(item.get("expires_at"), "expires_at")
            for item in items
            if item.get("expires_at")
        ]
        earliest_expiry = min(expiries) if expiries else None
        plans.append(
            CompressionGroup(
                group_key=key,
                source_ids=source_ids,
                summary_text=f"Memory summary [{key}] ({len(items)} items): {details}",
                tags=["summary", *tags],
                privacy=str(items[0]["privacy"]),
                expires_at=utc_iso(earliest_expiry) if earliest_expiry else None,
            )
        )
    return plans
