from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.config import (
    load_tool_settings,
    masked_tool_settings,
    update_tool_settings,
)
from nexus.integrations.core import JsonHttpClient, ToolError, ToolPermissionError
from nexus.integrations.manager import build_tool_manager
from nexus.service import NexusService
from nexus.store import JsonStore


ROOT = Path(__file__).resolve().parents[1]


class FakeHttp:
    def request_json(self, method: str, url: str, **kwargs: object) -> object:
        if "geocoding-api" in url:
            return {
                "results": [{
                    "name": "Shanghai",
                    "admin1": "Shanghai",
                    "country": "China",
                    "latitude": 31.23,
                    "longitude": 121.47,
                    "timezone": "Asia/Shanghai",
                }]
            }
        if "open-meteo.com/v1/forecast" in url:
            return {
                "timezone": "Asia/Shanghai",
                "current": {
                    "temperature_2m": 25,
                    "apparent_temperature": 27,
                    "weather_code": 1,
                    "wind_speed_10m": 8,
                },
                "daily": {
                    "temperature_2m_max": [29],
                    "temperature_2m_min": [21],
                    "precipitation_probability_max": [20],
                },
            }
        if "todoist.com" in url:
            return {
                "results": [{
                    "id": "todo-1",
                    "content": "Complete IELTS listening",
                    "description": "One practice set",
                    "priority": 4,
                    "due": {"date": "2030-01-03"},
                    "labels": ["study"],
                }],
                "next_cursor": None,
            }
        if url.endswith("/issues"):
            return [
                {"number": 7, "title": "Add tools", "updated_at": "2030-01-02T00:00:00Z", "html_url": "https://example/7"},
                {"number": 8, "title": "A pull request", "pull_request": {}, "updated_at": "2030-01-02T00:00:00Z"},
            ]
        if "api.github.com/repos/" in url:
            return {
                "description": "Personal AI",
                "default_branch": "main",
                "stargazers_count": 5,
                "forks_count": 1,
                "open_issues_count": 2,
            }
        if "api.notion.com" in url:
            return {
                "results": [{
                    "id": "page-1",
                    "last_edited_time": "2030-01-02T00:00:00Z",
                    "url": "https://notion.example/page-1",
                    "properties": {
                        "Name": {"title": [{"plain_text": "Research Notes"}]}
                    },
                }],
                "has_more": False,
            }
        raise AssertionError(f"Unexpected URL: {url}")

    def request_bytes(self, method: str, url: str, **kwargs: object) -> bytes:
        assert url == "https://calendar.example/private.ics"
        return b"""BEGIN:VCALENDAR\r
VERSION:2.0\r
BEGIN:VEVENT\r
UID:event-1\r
DTSTART:20300103T020000Z\r
DTEND:20300103T030000Z\r
SUMMARY:Operating Systems Review\r
LOCATION:Library\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:event-recurring\r
DTSTART:20291227T040000Z\r
DTEND:20291227T050000Z\r
RRULE:FREQ=WEEKLY;COUNT=3\r
SUMMARY:Weekly Research Meeting\r
END:VEVENT\r
END:VCALENDAR\r
"""


class FakeIMAP:
    def __init__(self, *args: object, **kwargs: object):
        self.logged_out = False

    def login(self, username: str, password: str) -> tuple[str, list[bytes]]:
        assert username == "louis@example.com"
        assert password == "mail-secret"
        return "OK", [b""]

    def select(self, mailbox: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        assert mailbox == "INBOX"
        assert readonly is True
        return "OK", [b"1"]

    def search(self, charset: object, criterion: str) -> tuple[str, list[bytes]]:
        assert criterion == "UNSEEN"
        return "OK", [b"1"]

    def fetch(self, message_id: bytes, query: str) -> tuple[str, list[object]]:
        raw = (
            b"Subject: Nexus research update\r\n"
            b"From: advisor@example.com\r\n"
            b"Date: Thu, 3 Jan 2030 08:00:00 +0000\r\n"
            b"Message-ID: <message-1@example.com>\r\n\r\n"
        )
        return "OK", [(b"header", raw)]

    def logout(self) -> tuple[str, list[bytes]]:
        self.logged_out = True
        return "BYE", [b""]


def enabled_settings(tmp_path: Path) -> dict[str, dict[str, object]]:
    root = tmp_path / "allowed"
    root.mkdir()
    return {
        "weather": {"enabled": True, "allowed_operations": ["read"], "location": "Shanghai"},
        "calendar": {"enabled": True, "allowed_operations": ["read"], "calendar_url": "https://calendar.example/private.ics"},
        "todo": {"enabled": True, "allowed_operations": ["read"], "token": "todo-secret"},
        "github": {"enabled": True, "allowed_operations": ["read"], "token": "github-secret", "repo": "LouissMa/Nexus"},
        "notion": {"enabled": True, "allowed_operations": ["read"], "token": "notion-secret"},
        "email": {
            "enabled": True,
            "allowed_operations": ["read"],
            "host": "imap.example.com",
            "port": 993,
            "username": "louis@example.com",
            "password": "mail-secret",
            "mailbox": "INBOX",
        },
        "filesystem": {
            "enabled": True,
            "allowed_operations": ["list", "read", "search"],
            "roots": [str(root)],
        },
    }


def test_web_personal_tools_permissions_and_audit(tmp_path: Path) -> None:
    settings = enabled_settings(tmp_path)
    manager = build_tool_manager(settings, tmp_path / "home", http_client=FakeHttp(), imap_factory=FakeIMAP)

    weather = manager.execute("weather", "read").data
    assert weather["temperature_c"] == 25
    assert "Shanghai" in weather["summary"]

    calendar = manager.execute("calendar", "read", days=2, now="2030-01-03T00:00:00+00:00").data
    assert calendar["events"][0]["summary"] == "Operating Systems Review"
    assert [event["summary"] for event in calendar["events"]] == [
        "Operating Systems Review",
        "Weekly Research Meeting",
    ]

    todo = manager.execute("todo", "read", limit=10).data
    assert todo["tasks"][0]["content"] == "Complete IELTS listening"

    github = manager.execute("github", "read", limit=10).data
    assert github["repository"] == "LouissMa/Nexus"
    assert [issue["number"] for issue in github["issues"]] == [7]

    notion = manager.execute("notion", "read", query="Research", limit=5).data
    assert notion["pages"][0]["title"] == "Research Notes"

    email = manager.execute("email", "read", limit=5, unread_only=True).data
    assert email["messages"][0]["subject"] == "Nexus research update"

    settings["github"]["enabled"] = False
    blocked = build_tool_manager(settings, tmp_path / "blocked-home", http_client=FakeHttp())
    with pytest.raises(ToolPermissionError):
        blocked.execute("github", "read")
    events = blocked.audit_events()
    assert events[0]["status"] == "error"
    assert "github-secret" not in json.dumps(events)


def test_filesystem_boundaries_and_search(tmp_path: Path) -> None:
    settings = enabled_settings(tmp_path)
    root = Path(settings["filesystem"]["roots"][0])
    note = root / "notes.md"
    note.write_text("Nexus tool integration\nSecond line", encoding="utf-8")
    manager = build_tool_manager(settings, tmp_path / "home", http_client=FakeHttp())

    listed = manager.execute("filesystem", "list", path=".").data
    assert listed["entries"][0]["name"] == "notes.md"
    read = manager.execute("filesystem", "read", path="notes.md").data
    assert "tool integration" in read["content"]
    searched = manager.execute("filesystem", "search", path=".", query="Nexus").data
    assert searched["matches"][0]["line"] == 1

    with pytest.raises(ToolPermissionError):
        manager.execute("filesystem", "read", path=str(tmp_path / "outside.txt"))


def test_http_response_limit_and_required_tool_config(tmp_path: Path) -> None:
    class OversizeResponse:
        def __enter__(self) -> "OversizeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, limit: int = -1) -> bytes:
            return b"1234"

    client = JsonHttpClient(
        max_response_bytes=3,
        opener=lambda *args, **kwargs: OversizeResponse(),
    )
    with pytest.raises(ToolError, match="exceeds"):
        client.request_bytes("GET", "https://example.test")

    with pytest.raises(ValueError, match="location"):
        update_tool_settings("weather", path=tmp_path / "config.local.json")

def test_tool_config_masking_cli_and_live_briefing(tmp_path: Path) -> None:
    config_path = tmp_path / "config.local.json"
    settings, _ = update_tool_settings(
        "github",
        {"token": "github-test-secret", "repo": "LouissMa/Nexus"},
        path=config_path,
    )
    shown = masked_tool_settings(settings)
    assert shown["github"]["token"] == "gith...cret"
    assert "github-test-secret" not in json.dumps(shown)
    assert load_tool_settings(env={}, path=config_path)["github"]["enabled"] is True

    allowed = tmp_path / "cli-files"
    allowed.mkdir()
    (allowed / "readme.txt").write_text("Nexus CLI tool", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["NEXUS_HOME"] = str(tmp_path / "nexus-home")
    subprocess.run(
        [sys.executable, "-m", "nexus.cli", "config", "tool", "set", "filesystem", "--root", str(allowed)],
        cwd=ROOT, env=env, check=True, capture_output=True, text=True,
    )
    result = subprocess.run(
        [sys.executable, "-m", "nexus.cli", "tool", "files", "read", "readme.txt"],
        cwd=ROOT, env=env, check=True, capture_output=True, text=True,
    )
    output = json.loads(result.stdout)
    assert output["result"]["data"]["content"] == "Nexus CLI tool"

    service = NexusService(JsonStore(tmp_path / "state.json"))
    briefing = service.daily_briefing(
        user_name="Louis",
        now=datetime(2030, 1, 3, 8, tzinfo=UTC),
        external_context={
            "weather": {"summary": "上海：晴，最高 29℃"},
            "calendar": [{"start": "2030-01-03T10:00:00+08:00", "summary": "OS Review", "location": "Library"}],
            "todos": [{"content": "IELTS listening", "due": "2030-01-03", "priority": 4}],
            "errors": [],
        },
        include_prompt=True,
    )
    assert briefing["today"]["weather"] == "上海：晴，最高 29℃"
    assert briefing["live_context"]["calendar"][0]["summary"] == "OS Review"
    assert "OS Review" in briefing["briefing"]
    assert "IELTS listening" in briefing["prompt"]["user"]
