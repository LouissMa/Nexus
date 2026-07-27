from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping
from urllib import request
from zoneinfo import ZoneInfo

from .runtime_config import ProfileSettings, RuntimeSettings


_PATH_LOCKS: dict[str, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


def _shared_path_lock(path: Path) -> threading.RLock:
    key = str(path.absolute()).casefold()
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


class NotificationCenter:
    """Persist notifications locally before attempting optional external channels."""

    MAX_TITLE_LENGTH = 240
    MAX_BODY_LENGTH = 4_000
    MAX_METADATA_BYTES = 2_048
    MAX_WEBHOOK_PAYLOAD_BYTES = 8_192
    WEBHOOK_TIMEOUT_SECONDS = 5.0
    TAIL_READ_BYTES = 64 * 1024

    _SECRET_KEY_PARTS = ("api_key", "authorization", "password", "secret", "token", "url")
    _URL_PATTERN = re.compile(r"https?://[^\s\"']+", re.IGNORECASE)
    _BEARER_PATTERN = re.compile(r"(Bearer\s+)\S+", re.IGNORECASE)
    _ASSIGNMENT_PATTERN = re.compile(
        r"((?:token|password|api[_-]?key|secret)=)[^&\s]+", re.IGNORECASE
    )
    _KEY_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")

    def __init__(
        self,
        path: Path,
        runtime: RuntimeSettings,
        profile: ProfileSettings,
        *,
        webhook_sender: Callable[[str, dict[str, Any], float], None] | None = None,
        console_writer: Callable[[str], None] | None = None,
        clock: Callable[[], datetime] | None = None,
        persist_hook: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.path = Path(path)
        self.runtime = runtime
        self.profile = profile
        self._timezone = ZoneInfo(profile.timezone)
        self._webhook_sender = webhook_sender or self._post_webhook
        self._console_writer = console_writer or print
        self._clock = clock or (lambda: datetime.now(UTC))
        self._persist_hook = persist_hook
        self._lock = _shared_path_lock(self.path)

    def publish(
        self,
        kind: str,
        title: str,
        body: str,
        *,
        urgency: str = "normal",
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            return self._publish_locked(
                kind, title, body, urgency=urgency, metadata=metadata
            )

    def _publish_locked(
        self,
        kind: str,
        title: str,
        body: str,
        *,
        urgency: str = "normal",
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if urgency not in {"normal", "urgent"}:
            raise ValueError("urgency must be 'normal' or 'urgent'.")
        defer_external = urgency != "urgent" and self.is_quiet_time()
        external_state = "deferred" if defer_external else "pending"
        record = {
            "id": uuid.uuid4().hex,
            "kind": self._bounded_text(kind, 100),
            "title": self._bounded_text(title, self.MAX_TITLE_LENGTH),
            "body": self._bounded_text(body, self.MAX_BODY_LENGTH),
            "created_at": self._utc_now().replace(microsecond=0).isoformat(),
            "urgency": urgency,
            "status": "stored",
            "delivery": {
                "inbox": {
                    "state": "delivered" if self.runtime.inbox_enabled else "disabled"
                },
                "console": {
                    "state": external_state if self.runtime.console_enabled else "disabled"
                },
                "webhook": {
                    "state": external_state if self.runtime.webhook_url else "disabled"
                },
            },
            "metadata": self._safe_metadata(metadata),
        }
        record["status"] = self._status_for(record)
        self._append(record)
        if self._persist_hook is not None:
            self._persist_hook(record)
        for channel in ("console", "webhook"):
            if record["delivery"][channel]["state"] == "pending":
                self._deliver_channel(record, channel)
        record["status"] = self._status_for(record)
        return record

    def flush_deferred(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._flush_deferred_locked()

    def _flush_deferred_locked(self) -> list[dict[str, Any]]:
        if self.is_quiet_time():
            return []

        records = [
            record for record in self._iter_records()
            if self._deferred_channels(record)
        ]
        flushed: list[dict[str, Any]] = []
        for record in records:
            for channel in self._deferred_channels(record):
                self._deliver_channel(record, channel)
            flushed.append(record)
        return flushed

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return self._recent_locked(limit)

    def _recent_locked(self, limit: int) -> list[dict[str, Any]]:
        if limit <= 0 or not self.path.exists():
            return []
        newest: list[dict[str, Any]] = []
        try:
            with self.path.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                position = handle.tell()
                partial = b""
                while position > 0 and len(newest) < limit:
                    size = min(self.TAIL_READ_BYTES, position)
                    position -= size
                    handle.seek(position)
                    partial = handle.read(size) + partial
                    lines = partial.split(b"\n")
                    partial = lines[0]
                    for raw_line in reversed(lines[1:]):
                        record = self._decode_record(raw_line)
                        if record is not None:
                            newest.append(record)
                            if len(newest) >= limit:
                                break
                if position == 0 and len(newest) < limit and partial:
                    record = self._decode_record(partial)
                    if record is not None:
                        newest.append(record)
        except OSError:
            return []
        return list(reversed(newest[:limit]))

    @staticmethod
    def _decode_record(raw_line: bytes) -> dict[str, Any] | None:
        try:
            record = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, TypeError, json.JSONDecodeError):
            return None
        if isinstance(record, dict) and isinstance(record.get("id"), str):
            return record
        return None
    def is_quiet_time(self, now: datetime | None = None) -> bool:
        start = self.runtime.quiet_hours_start
        end = self.runtime.quiet_hours_end
        if start is None or end is None:
            return False
        current = now or self._clock()
        if current.tzinfo is None:
            current = current.replace(tzinfo=self._timezone)
        local = current.astimezone(self._timezone)
        minute = local.hour * 60 + local.minute
        start_minute = self._clock_minutes(start)
        end_minute = self._clock_minutes(end)
        if start_minute < end_minute:
            return start_minute <= minute < end_minute
        return minute >= start_minute or minute < end_minute

    def _deliver_initial_channels(self, record: dict[str, Any], *, defer_external: bool) -> None:
        if self.runtime.console_enabled:
            if defer_external:
                record["delivery"]["console"] = {"state": "deferred"}
            else:
                self._deliver_channel(record, "console")
        if self.runtime.webhook_url:
            if defer_external:
                record["delivery"]["webhook"] = {"state": "deferred"}
            else:
                self._deliver_channel(record, "webhook")

    def _deliver_channel(self, record: dict[str, Any], channel: str) -> None:
        current = record.get("delivery", {}).get(channel, {}).get("state")
        if current not in {"pending", "deferred"}:
            return
        record["delivery"][channel] = {"state": "delivering"}
        record["status"] = self._status_for(record)
        self._replace_record(record)
        try:
            if channel == "console":
                self._console_writer(self._console_message(record))
            elif channel == "webhook":
                self._webhook_sender(
                    self.runtime.webhook_url or "",
                    self._webhook_payload(record),
                    self.WEBHOOK_TIMEOUT_SECONDS,
                )
            else:
                return
        except Exception:
            record["delivery"][channel] = {
                "state": "failed",
                "error": f"{channel}_delivery_failed",
            }
        else:
            record["delivery"][channel] = {"state": "delivered"}
        record["status"] = self._status_for(record)
        self._replace_record(record)
    def _append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())

    def _replace_record(self, updated: dict[str, Any]) -> None:
        if not self.path.exists():
            return
        temporary = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
        changed = False
        with self.path.open("r", encoding="utf-8") as source, temporary.open(
            "w", encoding="utf-8"
        ) as handle:
            for line in source:
                replacement = line
                try:
                    record = json.loads(line)
                except (TypeError, json.JSONDecodeError):
                    record = None
                if isinstance(record, dict) and record.get("id") == updated.get("id"):
                    replacement = (
                        json.dumps(updated, ensure_ascii=False, separators=(",", ":"))
                        + "\n"
                    )
                    changed = True
                handle.write(replacement)
            handle.flush()
            os.fsync(handle.fileno())
        if changed:
            os.replace(temporary, self.path)
        else:
            temporary.unlink(missing_ok=True)
    def _webhook_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = {
            key: record[key]
            for key in ("id", "kind", "title", "body", "created_at", "urgency", "metadata")
        }
        payload["idempotency_key"] = record["id"]
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) <= self.MAX_WEBHOOK_PAYLOAD_BYTES:
            return payload
        body = str(payload["body"])
        while body and len(encoded) > self.MAX_WEBHOOK_PAYLOAD_BYTES:
            body = body[: max(0, len(body) - 128)]
            payload["body"] = body
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return payload
    def _post_webhook(self, url: str, payload: dict[str, Any], timeout: float) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        http_request = request.Request(
            url,
            data=encoded,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": str(payload["id"]),
                "User-Agent": "Nexus-LifeAgent/0.1",
            },
        )
        with request.urlopen(http_request, timeout=timeout) as response:
            response.read(1)
    def _safe_metadata(self, metadata: Mapping[str, Any] | None) -> dict[str, Any]:
        if metadata is None:
            return {}
        sanitized = self._sanitize_value(dict(metadata))
        encoded = json.dumps(sanitized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > self.MAX_METADATA_BYTES:
            return {"truncated": True}
        return sanitized

    def _sanitize_value(self, value: Any, key: str = "") -> Any:
        normalized_key = key.lower()
        if any(part in normalized_key for part in self._SECRET_KEY_PARTS):
            return "***"
        if isinstance(value, Mapping):
            return {
                self._bounded_text(str(item_key), 100): self._sanitize_value(item, str(item_key))
                for item_key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self._sanitize_value(item) for item in value[:50]]
        if isinstance(value, str):
            return self._bounded_text(self._safe_error(value), 500)
        if isinstance(value, (bool, int, float)) or value is None:
            return value
        return self._bounded_text(self._safe_error(str(value)), 500)

    def _status_for(self, record: Mapping[str, Any]) -> str:
        delivery = record["delivery"]
        states = [item.get("state") for item in delivery.values() if isinstance(item, dict)]
        if "failed" in states:
            return "partial"
        if "delivering" in states or "pending" in states:
            return "pending"
        if "deferred" in states:
            return "deferred"
        if "delivered" in states:
            return "delivered"
        return "stored"

    def _iter_records(self) -> Iterator[dict[str, Any]]:
        if not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        record = json.loads(line)
                    except (TypeError, json.JSONDecodeError):
                        continue
                    if isinstance(record, dict) and isinstance(record.get("id"), str):
                        yield record
        except OSError:
            return

    @staticmethod
    def _deferred_channels(record: Mapping[str, Any]) -> list[str]:
        delivery = record.get("delivery", {})
        if not isinstance(delivery, Mapping):
            return []
        return [
            channel
            for channel in ("console", "webhook")
            if isinstance(delivery.get(channel), Mapping)
            and delivery[channel].get("state") == "deferred"
        ]

    def _utc_now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=self._timezone)
        return now.astimezone(UTC)

    @staticmethod
    def _bounded_text(value: Any, limit: int) -> str:
        return str(value).strip()[:limit]

    @staticmethod
    def _clock_minutes(value: str) -> int:
        hour, minute = value.split(":", 1)
        return int(hour) * 60 + int(minute)

    @staticmethod
    def _console_message(record: Mapping[str, Any]) -> str:
        return f"[{record['urgency']}] {record['title']}\n{record['body']}"

    @classmethod
    def _safe_error(cls, value: str) -> str:
        sanitized = cls._URL_PATTERN.sub("[redacted-url]", value)
        sanitized = cls._BEARER_PATTERN.sub(r"\1***", sanitized)
        sanitized = cls._ASSIGNMENT_PATTERN.sub(r"\1***", sanitized)
        return cls._KEY_PATTERN.sub("[redacted-key]", sanitized)[:500]
