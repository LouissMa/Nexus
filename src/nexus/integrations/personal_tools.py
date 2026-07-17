from __future__ import annotations

import imaplib
import ssl
from datetime import UTC, date, datetime, time, timedelta
from email import message_from_bytes
from email.header import decode_header, make_header
from pathlib import Path
from typing import Any, Callable

from .core import JsonHttpClient, ToolError, ToolPermissionError


class CalendarTool:
    name = "calendar"

    def __init__(self, config: dict[str, Any], http: JsonHttpClient):
        self.config = config
        self.http = http

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation != "read":
            raise ToolError("Calendar currently supports read-only event retrieval.")
        calendar_url = self.config.get("calendar_url")
        if not calendar_url:
            raise ToolError("Calendar iCalendar feed URL is not configured.")
        try:
            from icalendar import Calendar
            import recurring_ical_events
        except (ImportError, ModuleNotFoundError) as exc:
            raise ToolError(
                "Calendar support is not installed. Run `python -m pip install -e .[tools]`."
            ) from exc

        now = self._parse_now(arguments.get("now"))
        days = min(max(int(arguments.get("days", 2)), 1), 31)
        end = now + timedelta(days=days)
        calendar = Calendar.from_ical(self.http.request_bytes("GET", calendar_url))
        components = recurring_ical_events.of(calendar, skip_bad_series=True).between(
            now, end
        )
        events: list[dict[str, Any]] = []
        for component in components:
            start = self._as_datetime(component.decoded("DTSTART"))
            raw_end = component.get("DTEND")
            event_end = (
                self._as_datetime(component.decoded("DTEND")) if raw_end else start
            )
            if event_end < now or start > end:
                continue
            events.append(
                {
                    "summary": str(component.get("SUMMARY", "Untitled event")),
                    "start": start.isoformat(),
                    "end": event_end.isoformat(),
                    "location": str(component.get("LOCATION", "")),
                    "all_day": isinstance(component.decoded("DTSTART"), date)
                    and not isinstance(component.decoded("DTSTART"), datetime),
                }
            )
        events.sort(key=lambda item: item["start"])
        return {"events": events, "count": len(events), "days": days}

    @staticmethod
    def _parse_now(value: str | None) -> datetime:
        if not value:
            return datetime.now(UTC)
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    @staticmethod
    def _as_datetime(value: date | datetime) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        return datetime.combine(value, time.min, tzinfo=UTC)


class EmailTool:
    name = "email"

    def __init__(
        self,
        config: dict[str, Any],
        imap_factory: Callable[..., Any] | None = None,
    ):
        self.config = config
        self.imap_factory = imap_factory or imaplib.IMAP4_SSL

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation != "read":
            raise ToolError("Email currently supports read-only header retrieval.")
        required = ["host", "username", "password"]
        missing = [key for key in required if not self.config.get(key)]
        if missing:
            raise ToolError(f"Email configuration is missing: {', '.join(missing)}.")
        limit = min(max(int(arguments.get("limit", 10)), 1), 50)
        unread_only = bool(arguments.get("unread_only", True))
        mailbox_name = self.config.get("mailbox", "INBOX")
        client = None
        try:
            client = self.imap_factory(
                self.config["host"],
                int(self.config.get("port", 993)),
                ssl_context=ssl.create_default_context(),
                timeout=int(self.config.get("timeout_seconds", 20)),
            )
            client.login(self.config["username"], self.config["password"])
            status, _ = client.select(mailbox_name, readonly=True)
            if status != "OK":
                raise ToolError(f"Unable to open IMAP mailbox '{mailbox_name}'.")
            status, data = client.search(None, "UNSEEN" if unread_only else "ALL")
            if status != "OK":
                raise ToolError("IMAP search failed.")
            message_ids = data[0].split()[-limit:]
            messages = []
            for message_id in reversed(message_ids):
                status, fetched = client.fetch(
                    message_id,
                    "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE MESSAGE-ID)])",
                )
                if status != "OK":
                    continue
                raw = next(
                    (item[1] for item in fetched if isinstance(item, tuple)), None
                )
                if not raw:
                    continue
                message = message_from_bytes(raw)
                messages.append(
                    {
                        "subject": self._decode(message.get("Subject", "")),
                        "from": self._decode(message.get("From", "")),
                        "date": message.get("Date"),
                        "message_id": message.get("Message-ID"),
                    }
                )
            return {
                "mailbox": mailbox_name,
                "unread_only": unread_only,
                "messages": messages,
                "count": len(messages),
            }
        except ToolError:
            raise
        except (imaplib.IMAP4.error, OSError, ssl.SSLError) as exc:
            raise ToolError(f"IMAP request failed: {exc}") from exc
        finally:
            if client is not None:
                try:
                    client.logout()
                except Exception:
                    pass

    @staticmethod
    def _decode(value: str) -> str:
        try:
            return str(make_header(decode_header(value)))
        except (LookupError, UnicodeError):
            return value


class FilesystemTool:
    name = "filesystem"
    TEXT_EXTENSIONS = {
        ".txt",
        ".md",
        ".py",
        ".json",
        ".toml",
        ".yaml",
        ".yml",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".html",
        ".css",
        ".csv",
        ".log",
    }

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.roots = [
            Path(root).expanduser().resolve() for root in config.get("roots", [])
        ]

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.roots:
            raise ToolError("No filesystem roots are configured.")
        target = self._resolve(arguments.get("path", "."))
        if operation == "list":
            if not target.is_dir():
                raise ToolError(f"'{target}' is not a directory.")
            entries = [
                {
                    "name": item.name,
                    "path": str(item),
                    "type": "directory" if item.is_dir() else "file",
                }
                for item in sorted(
                    target.iterdir(),
                    key=lambda item: (not item.is_dir(), item.name.lower()),
                )
            ]
            return {
                "path": str(target),
                "entries": entries[:200],
                "count": len(entries),
            }
        if operation == "read":
            if not target.is_file():
                raise ToolError(f"'{target}' is not a file.")
            max_bytes = min(max(int(arguments.get("max_bytes", 65536)), 1), 1_000_000)
            raw = target.read_bytes()[:max_bytes]
            return {
                "path": str(target),
                "content": raw.decode("utf-8", errors="replace"),
                "truncated": target.stat().st_size > len(raw),
                "bytes": len(raw),
            }
        if operation == "search":
            query = str(arguments.get("query", "")).lower().strip()
            if not query:
                raise ToolError("Filesystem search query is required.")
            base = target if target.is_dir() else target.parent
            matches = []
            scanned = 0
            for path in base.rglob("*"):
                if len(matches) >= 100 or scanned >= 1000:
                    break
                if (
                    not path.is_file()
                    or path.suffix.lower() not in self.TEXT_EXTENSIONS
                ):
                    continue
                resolved_path = path.resolve()
                if not any(
                    resolved_path == root or resolved_path.is_relative_to(root)
                    for root in self.roots
                ):
                    continue
                path = resolved_path
                scanned += 1
                try:
                    if path.stat().st_size > 1_000_000:
                        continue
                    for line_number, line in enumerate(
                        path.read_text(encoding="utf-8", errors="replace").splitlines(),
                        1,
                    ):
                        if query in line.lower():
                            matches.append(
                                {
                                    "path": str(path),
                                    "line": line_number,
                                    "text": line[:300],
                                }
                            )
                            if len(matches) >= 100:
                                break
                except OSError:
                    continue
            return {
                "path": str(base),
                "query": arguments["query"],
                "matches": matches,
                "scanned_files": scanned,
            }
        raise ToolError(f"Unknown filesystem operation '{operation}'.")

    def _resolve(self, value: str) -> Path:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = self.roots[0] / candidate
        resolved = candidate.resolve()
        if not any(
            resolved == root or resolved.is_relative_to(root) for root in self.roots
        ):
            raise ToolPermissionError(
                f"Path '{resolved}' is outside configured filesystem roots."
            )
        return resolved
