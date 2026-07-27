from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pytest

import nexus.notifications as notification_module
from nexus.notifications import NotificationCenter
from nexus.runtime_config import ProfileSettings, RuntimeSettings


def _center(
    tmp_path: Path,
    *,
    runtime: RuntimeSettings | None = None,
    clock: datetime | Callable[[], datetime] | None = None,
    webhook_sender=None,
    console_writer=None,
) -> NotificationCenter:
    return NotificationCenter(
        tmp_path / "notifications.jsonl",
        runtime or RuntimeSettings(),
        ProfileSettings(display_name="Ava", timezone="Asia/Shanghai"),
        clock=clock if callable(clock) else ((lambda: clock) if clock else None),
        webhook_sender=webhook_sender,
        console_writer=console_writer,
    )


def _local_time(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, 27, hour, minute, tzinfo=ZoneInfo("Asia/Shanghai"))


def _stored_record(notification_id: str, *, webhook_state: str = "delivered") -> dict[str, Any]:
    status = "deferred" if webhook_state == "deferred" else "delivered"
    return {
        "id": notification_id,
        "kind": "reminder",
        "title": f"Title {notification_id}",
        "body": "Body",
        "created_at": "2026-07-27T00:00:00+00:00",
        "urgency": "normal",
        "status": status,
        "delivery": {
            "inbox": {"state": "delivered"},
            "console": {"state": "disabled"},
            "webhook": {"state": webhook_state},
        },
        "metadata": {},
    }


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )


def test_publish_persists_inbox_record_before_external_delivery_when_inbox_is_disabled(
    tmp_path: Path,
) -> None:
    delivered: list[dict[str, object]] = []
    center = _center(
        tmp_path,
        runtime=RuntimeSettings(inbox_enabled=False, webhook_url="https://hooks.example.test/a"),
        webhook_sender=lambda url, payload, timeout: delivered.append(payload),
    )

    record = center.publish("reminder", "Review plan", "The daily plan needs attention.")

    persisted = json.loads((tmp_path / "notifications.jsonl").read_text(encoding="utf-8"))
    assert persisted["id"] == record["id"]
    assert persisted["delivery"]["inbox"]["state"] == "disabled"
    assert record["status"] == "delivered"
    assert delivered[0]["id"] == record["id"]


def test_quiet_hours_defer_non_urgent_external_delivery(tmp_path: Path) -> None:
    console: list[str] = []
    webhook_calls: list[dict[str, object]] = []
    center = _center(
        tmp_path,
        runtime=RuntimeSettings(
            console_enabled=True,
            webhook_url="https://hooks.example.test/a",
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
        ),
        clock=_local_time(23),
        console_writer=console.append,
        webhook_sender=lambda url, payload, timeout: webhook_calls.append(payload),
    )

    record = center.publish("briefing", "Evening briefing", "A short update.")

    assert record["status"] == "deferred"
    assert record["delivery"]["console"]["state"] == "deferred"
    assert record["delivery"]["webhook"]["state"] == "deferred"
    assert console == []
    assert webhook_calls == []


def test_quiet_time_supports_same_day_and_overnight_ranges(tmp_path: Path) -> None:
    same_day = _center(
        tmp_path,
        runtime=RuntimeSettings(quiet_hours_start="12:00", quiet_hours_end="13:00"),
        clock=_local_time(12, 30),
    )
    overnight = _center(
        tmp_path,
        runtime=RuntimeSettings(quiet_hours_start="22:00", quiet_hours_end="07:00"),
        clock=_local_time(6, 30),
    )

    assert same_day.is_quiet_time() is True
    assert same_day.is_quiet_time(_local_time(13)) is False
    assert overnight.is_quiet_time() is True
    assert overnight.is_quiet_time(_local_time(12)) is False


def test_urgent_notifications_bypass_quiet_hours(tmp_path: Path) -> None:
    console: list[str] = []
    center = _center(
        tmp_path,
        runtime=RuntimeSettings(
            console_enabled=True,
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
        ),
        clock=_local_time(23),
        console_writer=console.append,
    )

    record = center.publish("alert", "Urgent", "Act now.", urgency="urgent")

    assert record["status"] == "delivered"
    assert record["delivery"]["console"]["state"] == "delivered"
    assert console == ["[urgent] Urgent\nAct now."]


def test_webhook_and_console_failures_are_isolated_and_sanitized(tmp_path: Path) -> None:
    def fail_webhook(url: str, payload: dict[str, object], timeout: float) -> None:
        raise RuntimeError(f"delivery to {url} with Bearer top-secret failed")

    def fail_console(message: str) -> None:
        raise RuntimeError("console is unavailable")

    url = "https://hooks.example.test/secret-token"
    center = _center(
        tmp_path,
        runtime=RuntimeSettings(console_enabled=True, webhook_url=url),
        webhook_sender=fail_webhook,
        console_writer=fail_console,
    )

    record = center.publish("reminder", "Review", "Check this today.")

    assert record["status"] == "partial"
    assert record["delivery"]["inbox"]["state"] == "delivered"
    assert record["delivery"]["console"]["state"] == "failed"
    assert record["delivery"]["webhook"]["state"] == "failed"
    assert record["delivery"]["console"]["error"] == "console_delivery_failed"
    assert record["delivery"]["webhook"]["error"] == "webhook_delivery_failed"
    assert url not in json.dumps(record)
    assert "top-secret" not in json.dumps(record)
    assert "unavailable" not in json.dumps(record)
    assert center.recent() == [record]


def test_flush_deferred_delivers_each_external_channel_once_after_quiet_hours(
    tmp_path: Path,
) -> None:
    now = [_local_time(23)]
    console: list[str] = []
    webhook_calls: list[dict[str, object]] = []
    center = _center(
        tmp_path,
        runtime=RuntimeSettings(
            console_enabled=True,
            webhook_url="https://hooks.example.test/a",
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
        ),
        clock=lambda: now[0],
        console_writer=console.append,
        webhook_sender=lambda url, payload, timeout: webhook_calls.append(payload),
    )
    original = center.publish("briefing", "Evening", "Details.")

    now[0] = _local_time(8)
    flushed = center.flush_deferred()
    flushed_again = center.flush_deferred()

    assert [record["id"] for record in flushed] == [original["id"]]
    assert flushed_again == []
    assert console == ["[normal] Evening\nDetails."]
    assert [payload["id"] for payload in webhook_calls] == [original["id"]]
    recent = center.recent()
    assert len(recent) == 1
    assert recent[0]["status"] == "delivered"


def test_recent_skips_corrupt_jsonl_lines_and_safe_metadata_and_content_are_bounded(
    tmp_path: Path,
) -> None:
    path = tmp_path / "notifications.jsonl"
    path.write_text("{this is corrupt}\n", encoding="utf-8")
    center = _center(tmp_path)

    record = center.publish(
        "note",
        "T" * 500,
        "B" * 10_000,
        metadata={
            "project": "Nexus",
            "webhook_url": "https://hooks.example.test/secret",
            "api_key": "top-secret",
        },
    )

    assert len(record["title"]) <= NotificationCenter.MAX_TITLE_LENGTH
    assert len(record["body"]) <= NotificationCenter.MAX_BODY_LENGTH
    assert record["metadata"] == {"project": "Nexus", "webhook_url": "***", "api_key": "***"}
    assert center.recent() == [record]
    assert path.read_text(encoding="utf-8").startswith("{this is corrupt}\n")


def test_publish_persists_pending_then_delivering_before_webhook_side_effect(
    tmp_path: Path,
) -> None:
    path = tmp_path / "notifications.jsonl"
    observed_states: list[str] = []

    def observe_initial_persist(record: dict[str, Any]) -> None:
        persisted = json.loads(path.read_text(encoding="utf-8"))
        observed_states.append(persisted["delivery"]["webhook"]["state"])

    def observe_delivery(url: str, payload: dict[str, Any], timeout: float) -> None:
        persisted = json.loads(path.read_text(encoding="utf-8"))
        observed_states.append(persisted["delivery"]["webhook"]["state"])

    center = NotificationCenter(
        path,
        RuntimeSettings(webhook_url="https://hooks.example.test/a"),
        ProfileSettings(timezone="Asia/Shanghai"),
        persist_hook=observe_initial_persist,
        webhook_sender=observe_delivery,
    )

    record = center.publish("reminder", "Review", "Check this today.")

    assert observed_states == ["pending", "delivering"]
    assert record["delivery"]["webhook"]["state"] == "delivered"


def test_quiet_publish_persists_deferred_intent_before_returning(tmp_path: Path) -> None:
    path = tmp_path / "notifications.jsonl"
    observed_states: list[str] = []
    sender_calls: list[str] = []

    def observe_initial_persist(record: dict[str, Any]) -> None:
        persisted = json.loads(path.read_text(encoding="utf-8"))
        observed_states.append(persisted["delivery"]["webhook"]["state"])

    center = NotificationCenter(
        path,
        RuntimeSettings(
            webhook_url="https://hooks.example.test/a",
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
        ),
        ProfileSettings(timezone="Asia/Shanghai"),
        persist_hook=observe_initial_persist,
        clock=lambda: _local_time(23),
        webhook_sender=lambda url, payload, timeout: sender_calls.append(payload["id"]),
    )

    record = center.publish("reminder", "Review", "Check this today.")

    assert observed_states == ["deferred"]
    assert record["delivery"]["webhook"]["state"] == "deferred"
    assert sender_calls == []


def test_interrupted_delivery_remains_delivering_and_is_not_automatically_retried(
    tmp_path: Path,
) -> None:
    class DeliveryInterrupted(BaseException):
        pass

    path = tmp_path / "notifications.jsonl"
    runtime = RuntimeSettings(webhook_url="https://hooks.example.test/a")

    def interrupt(url: str, payload: dict[str, Any], timeout: float) -> None:
        raise DeliveryInterrupted

    center = NotificationCenter(
        path,
        runtime,
        ProfileSettings(timezone="Asia/Shanghai"),
        webhook_sender=interrupt,
    )

    with pytest.raises(DeliveryInterrupted):
        center.publish("reminder", "Review", "Check this today.")

    persisted = center.recent()
    assert len(persisted) == 1
    assert persisted[0]["delivery"]["webhook"]["state"] == "delivering"

    retry_calls: list[str] = []
    recovered = NotificationCenter(
        path,
        runtime,
        ProfileSettings(timezone="Asia/Shanghai"),
        webhook_sender=lambda url, payload, timeout: retry_calls.append(payload["id"]),
    )
    assert recovered.flush_deferred() == []
    assert retry_calls == []
    assert recovered.recent()[0]["delivery"]["webhook"]["state"] == "delivering"


def test_concurrent_flushes_deliver_a_deferred_channel_exactly_once(tmp_path: Path) -> None:
    now = [_local_time(23)]
    sender_calls: list[str] = []
    sender_lock = threading.Lock()
    start = threading.Barrier(3)

    def sender(url: str, payload: dict[str, Any], timeout: float) -> None:
        with sender_lock:
            sender_calls.append(payload["id"])
        time.sleep(0.05)

    center = _center(
        tmp_path,
        runtime=RuntimeSettings(
            webhook_url="https://hooks.example.test/a",
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
        ),
        clock=lambda: now[0],
        webhook_sender=sender,
    )
    record = center.publish("reminder", "Review", "Check this today.")
    now[0] = _local_time(8)

    def flush() -> list[dict[str, Any]]:
        start.wait()
        return center.flush_deferred()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(flush) for _ in range(2)]
        start.wait()
        results = [future.result() for future in futures]

    assert sender_calls == [record["id"]]
    assert sorted(len(result) for result in results) == [0, 1]


def test_two_centers_sharing_a_path_flush_deferred_exactly_once(tmp_path: Path) -> None:
    path = tmp_path / "notifications.jsonl"
    now = [_local_time(23)]
    calls: list[str] = []
    calls_lock = threading.Lock()
    runtime = RuntimeSettings(
        webhook_url="https://hooks.example.test/a",
        quiet_hours_start="22:00",
        quiet_hours_end="07:00",
    )

    def sender(url: str, payload: dict[str, Any], timeout: float) -> None:
        with calls_lock:
            calls.append(payload["id"])
        time.sleep(0.05)

    first = NotificationCenter(
        path,
        runtime,
        ProfileSettings(timezone="Asia/Shanghai"),
        clock=lambda: now[0],
        webhook_sender=sender,
    )
    second = NotificationCenter(
        path,
        runtime,
        ProfileSettings(timezone="Asia/Shanghai"),
        clock=lambda: now[0],
        webhook_sender=sender,
    )
    record = first.publish("reminder", "Review", "Check this today.")
    now[0] = _local_time(8)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda center: center.flush_deferred(), (first, second)))

    assert calls == [record["id"]]
    assert sorted(len(result) for result in results) == [0, 1]


def test_recent_reads_past_many_malformed_tail_lines(tmp_path: Path) -> None:
    path = tmp_path / "notifications.jsonl"
    _write_jsonl(path, [_stored_record("valid-before-corruption")])
    with path.open("a", encoding="utf-8") as handle:
        handle.writelines("{malformed}\n" for _ in range(10_000))
    center = NotificationCenter(
        path,
        RuntimeSettings(),
        ProfileSettings(timezone="Asia/Shanghai"),
    )

    assert [record["id"] for record in center.recent(1)] == ["valid-before-corruption"]

def test_rewrite_preserves_more_than_10000_records(tmp_path: Path) -> None:
    path = tmp_path / "notifications.jsonl"
    records = [_stored_record(f"old-{index}") for index in range(10_001)]
    records.append(_stored_record("deferred-last", webhook_state="deferred"))
    _write_jsonl(path, records)
    sender_calls: list[str] = []
    center = NotificationCenter(
        path,
        RuntimeSettings(webhook_url="https://hooks.example.test/a"),
        ProfileSettings(timezone="Asia/Shanghai"),
        webhook_sender=lambda url, payload, timeout: sender_calls.append(payload["id"]),
    )

    center.flush_deferred()

    raw_lines = path.read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 10_002
    assert json.loads(raw_lines[0])["id"] == "old-0"
    assert json.loads(raw_lines[-1])["delivery"]["webhook"]["state"] == "delivered"
    assert sender_calls == ["deferred-last"]


def test_flush_considers_deferred_records_before_the_last_10000(tmp_path: Path) -> None:
    path = tmp_path / "notifications.jsonl"
    records = [_stored_record("deferred-first", webhook_state="deferred")]
    records.extend(_stored_record(f"new-{index}") for index in range(10_001))
    _write_jsonl(path, records)
    sender_calls: list[str] = []
    center = NotificationCenter(
        path,
        RuntimeSettings(webhook_url="https://hooks.example.test/a"),
        ProfileSettings(timezone="Asia/Shanghai"),
        webhook_sender=lambda url, payload, timeout: sender_calls.append(payload["id"]),
    )

    flushed = center.flush_deferred()

    assert [record["id"] for record in flushed] == ["deferred-first"]
    assert sender_calls == ["deferred-first"]
    assert len(path.read_text(encoding="utf-8").splitlines()) == 10_002


def test_recent_uses_bounded_tail_reads_and_skips_malformed_tail_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "notifications.jsonl"
    records = [_stored_record(f"item-{index}") for index in range(200)]
    _write_jsonl(path, records)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{malformed tail}\n")
    center = NotificationCenter(
        path,
        RuntimeSettings(),
        ProfileSettings(timezone="Asia/Shanghai"),
    )

    def forbid_full_read(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("recent() must not read the entire JSONL file")

    monkeypatch.setattr(Path, "read_text", forbid_full_read)

    assert [record["id"] for record in center.recent(2)] == ["item-198", "item-199"]


def test_webhook_payload_is_byte_bounded_and_timeout_is_propagated(tmp_path: Path) -> None:
    calls: list[tuple[dict[str, Any], float]] = []
    center = _center(
        tmp_path,
        runtime=RuntimeSettings(webhook_url="https://hooks.example.test/a"),
        webhook_sender=lambda url, payload, timeout: calls.append((payload, timeout)),
    )

    record = center.publish("reminder", "Review", "?" * 10_000)

    payload, timeout = calls[0]
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert len(encoded) <= NotificationCenter.MAX_WEBHOOK_PAYLOAD_BYTES
    assert timeout == NotificationCenter.WEBHOOK_TIMEOUT_SECONDS
    assert payload["id"] == record["id"]
    assert payload["idempotency_key"] == record["id"]


def test_default_webhook_post_uses_notification_id_as_idempotency_header(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int) -> bytes:
            return b""

    def urlopen(http_request: Any, *, timeout: float) -> Response:
        captured["request"] = http_request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(notification_module.request, "urlopen", urlopen)
    center = _center(
        tmp_path,
        runtime=RuntimeSettings(webhook_url="https://hooks.example.test/a"),
    )

    record = center.publish("reminder", "Review", "Check this today.")

    http_request = captured["request"]
    payload = json.loads(http_request.data.decode("utf-8"))
    assert http_request.get_header("Idempotency-key") == record["id"]
    assert payload["id"] == record["id"]
    assert payload["idempotency_key"] == record["id"]
    assert captured["timeout"] == NotificationCenter.WEBHOOK_TIMEOUT_SECONDS
