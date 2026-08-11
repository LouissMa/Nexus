from __future__ import annotations

import json
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from nexus.dashboard import DashboardServer, DashboardSnapshot
from nexus.integrations.core import AuditLogger


NOW = datetime(2026, 7, 27, 8, 30, tzinfo=UTC)
SECRET = "sk-dashboard-secret-123456789"
WEBHOOK = "https://hooks.example.test/private-token"


class RecentSource:
    def __init__(
        self, records: list[Any] | None = None, error: Exception | None = None
    ):
        self.records = records or []
        self.error = error

    def recent(self, limit: int = 50) -> list[Any]:
        if self.error is not None:
            raise self.error
        return self.records[-limit:]


def memory(
    memory_id: str,
    text: str,
    *,
    status: str = "active",
    expires_at: str | None = None,
) -> dict[str, Any]:
    return {
        "id": memory_id,
        "text": text,
        "tags": ["nexus", "research"],
        "created_at": "2026-07-20T08:00:00+00:00",
        "updated_at": "2026-07-20T08:00:00+00:00",
        "privacy": "private",
        "importance": 0.8,
        "importance_source": "user",
        "pinned": False,
        "status": status,
        "expires_at": expires_at,
    }


def state_payload() -> dict[str, Any]:
    return {
        "daily_tasks": [
            {
                "id": "task-1",
                "plan_date": "2026-07-27",
                "title": "Finish dashboard snapshot",
                "status": "pending",
                "priority": 1,
                "estimated_minutes": 45,
                "prompt": "do not expose this prompt",
            }
        ],
        "goals": [
            {
                "id": "goal-1",
                "title": "Ship Nexus",
                "description": f"Keep credentials private: {SECRET}",
                "cadence_days": 3,
                "status": "active",
                "created_at": "2026-07-01T00:00:00+00:00",
                "last_check_in": "2026-07-26T12:00:00+00:00",
                "check_ins": [{"at": "2026-07-26T12:00:00+00:00", "note": "steady"}],
            }
        ],
        "memories": [
            memory("active", "Nexus dashboard decisions"),
            memory("forgotten", "forgotten private text", status="forgotten"),
            memory(
                "expired",
                "expired private text",
                expires_at="2026-07-26T00:00:00+00:00",
            ),
            memory("secret", f"A credential appeared here: {SECRET}"),
        ],
    }


def scheduler_payload() -> dict[str, Any]:
    return {
        "next_occurrence": "2026-07-27T20:00:00+00:00",
        "schedule": {
            "timezone": "UTC",
            "jobs": {
                "morning_briefing": {
                    "enabled": True,
                    "time": "08:00",
                    "next_occurrence": "2026-07-28T08:00:00+00:00",
                }
            },
        },
        "health": {"notification_flush_failures": 0, "last_tick_error": None},
        "runtime": {
            "webhook_url": "***configured***",
            "enabled_jobs": ["morning_briefing"],
        },
    }


def make_snapshot(**overrides: Any) -> DashboardSnapshot:
    values: dict[str, Any] = {
        "state_source": state_payload,
        "notifications": RecentSource(
            [
                {
                    "id": "notice-1",
                    "kind": "briefing",
                    "title": "Morning briefing",
                    "body": f"Ready. token={SECRET}",
                    "created_at": "2026-07-27T08:00:00+00:00",
                    "status": "delivered",
                    "delivery": {"inbox": {"state": "delivered"}},
                    "metadata": {"webhook_url": WEBHOOK},
                }
            ]
        ),
        "tool_audit": RecentSource(
            [
                {
                    "at": "2026-07-27T08:10:00+00:00",
                    "tool": "filesystem",
                    "operation": "read",
                    "status": "ok",
                    "arguments": {"path": "private.txt"},
                    "output": "private command output",
                }
            ]
        ),
        "mcp_audit": RecentSource(
            [
                {
                    "at": "2026-07-27T08:11:00+00:00",
                    "action": "call",
                    "server": "research",
                    "tool": "search",
                    "status": "ok",
                    "prompt": "private MCP prompt",
                }
            ]
        ),
        "agent_traces": RecentSource(
            [
                {
                    "run_id": "run-1",
                    "workflow": "daily_plan",
                    "status": "success",
                    "duration_ms": 12,
                    "prompt": "private agent prompt",
                }
            ]
        ),
        "automation_audit": RecentSource(
            [
                {
                    "at": "2026-07-27T08:12:00+00:00",
                    "action": "digest:abc",
                    "type": "command",
                    "policy": "ask",
                    "decision": "approved",
                    "status": "success",
                    "duration_ms": 20,
                    "argv": ["pwsh", "-Command", "Get-Secret"],
                    "env": {"API_KEY": SECRET},
                }
            ]
        ),
        "scheduler_status": scheduler_payload,
        "settings": lambda: {
            "profile": {"display_name": "Louis", "timezone": "UTC"},
            "runtime": {"webhook_url": WEBHOOK, "coach_mode": "gentle"},
            "llm": {
                "provider": "deepseek",
                "api_key": SECRET,
                "simple_model": "v4flash",
            },
            "tools": {"github": {"enabled": True, "token": SECRET}},
        },
        "clock": lambda: NOW,
    }
    values.update(overrides)
    return DashboardSnapshot(**values)


def test_snapshot_builds_all_views_and_filters_private_data() -> None:
    result = make_snapshot().build()

    assert result["generated_at"] == "2026-07-27T08:30:00+00:00"
    assert set(result["sections"]) == {
        "today",
        "goals",
        "habits",
        "projects",
        "suggestions",
        "memory",
        "activity",
        "settings",
    }
    assert all(section["status"] == "ok" for section in result["sections"].values())
    assert (
        result["sections"]["today"]["data"]["tasks"][0]["title"]
        == "Finish dashboard snapshot"
    )
    assert result["sections"]["goals"]["data"]["items"][0]["title"] == "Ship Nexus"

    memories = result["sections"]["memory"]["data"]["items"]
    assert {item["id"] for item in memories} == {"active", "secret"}
    assert memories[0]["privacy"] == "private"

    serialized = json.dumps(result, ensure_ascii=False)
    for forbidden in (
        SECRET,
        WEBHOOK,
        "forgotten private text",
        "expired private text",
        "private command output",
        "private MCP prompt",
        "private agent prompt",
        "Get-Secret",
        "do not expose this prompt",
        "private.txt",
    ):
        assert forbidden not in serialized
    assert "***configured***" in serialized or "[redacted]" in serialized


def test_corrupt_jsonl_entries_are_skipped(tmp_path: Path) -> None:
    audit_path = tmp_path / "tool-audit.jsonl"
    audit_path.write_text(
        '{"at":"2026-07-27T08:00:00Z","tool":"weather","operation":"read","status":"ok"}\n'
        "not-json\n"
        '{"at":"2026-07-27T08:01:00Z","tool":"calendar","operation":"read","status":"ok"}\n',
        encoding="utf-8",
    )

    result = make_snapshot(tool_audit=AuditLogger(audit_path)).build()
    tool_events = result["sections"]["activity"]["data"]["tools"]

    assert [event["tool"] for event in tool_events] == ["weather", "calendar"]


def test_section_failures_are_isolated_and_public() -> None:
    result = make_snapshot(
        tool_audit=RecentSource(error=RuntimeError(f"database failed: {SECRET}"))
    ).build()

    assert result["sections"]["activity"] == {
        "status": "error",
        "data": None,
        "error": "activity_unavailable",
    }
    assert result["sections"]["today"]["status"] == "ok"
    assert result["sections"]["settings"]["status"] == "ok"
    assert SECRET not in json.dumps(result)


def request(url: str) -> tuple[int, dict[str, str], bytes]:
    with urllib.request.urlopen(url, timeout=3) as response:
        return response.status, dict(response.headers.items()), response.read()


def test_server_serves_exact_routes_mime_and_security_headers() -> None:
    server = DashboardServer(make_snapshot(), port=0)
    with server:
        assert server.host == "127.0.0.1"
        assert server.port > 0
        for route, content_type in (
            ("/", "text/html"),
            ("/index.html", "text/html"),
            ("/dashboard.css", "text/css"),
            ("/dashboard.js", "text/javascript"),
            ("/api/snapshot", "application/json"),
        ):
            status, headers, body = request(server.url + route)
            assert status == 200
            assert headers["Content-Type"].startswith(content_type)
            assert headers["Cache-Control"] == "no-store"
            assert headers["X-Content-Type-Options"] == "nosniff"
            assert headers["X-Frame-Options"] == "DENY"
            assert headers["Referrer-Policy"] == "no-referrer"
            assert headers["Content-Security-Policy"]
            assert body

        payload = json.loads(request(server.url + "/api/snapshot")[2])
        assert payload["sections"]["today"]["status"] == "ok"


@pytest.mark.parametrize(
    "path",
    [
        "/missing",
        "/dashboard.css/extra",
        "/../pyproject.toml",
        "/%2e%2e/pyproject.toml",
        "/dashboard/%2e%2e/dashboard.py",
    ],
)
def test_server_rejects_unknown_and_traversal_paths(path: str) -> None:
    with DashboardServer(make_snapshot(), port=0) as server:
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(server.url + path, timeout=3)
        assert error.value.code == 404


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.25", "example.com"])
def test_server_rejects_non_loopback_bindings(host: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        DashboardServer(make_snapshot(), host=host, port=0)


def test_server_supports_ephemeral_port_and_clean_shutdown() -> None:
    server = DashboardServer(make_snapshot(), port=0)
    server.start()
    url = server.url
    assert request(url + "/api/snapshot")[0] == 200

    server.shutdown()
    server.shutdown()
    deadline = time.monotonic() + 2
    while server.is_running and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not server.is_running
    with pytest.raises(OSError):
        urllib.request.urlopen(url + "/api/snapshot", timeout=0.2)


def test_packaged_index_references_local_accessible_assets() -> None:
    assets = Path(__file__).parents[1] / "src" / "nexus" / "dashboard"
    html = (assets / "index.html").read_text(encoding="utf-8")
    script = (assets / "dashboard.js").read_text(encoding="utf-8")

    assert 'href="/dashboard.css"' in html
    assert 'src="/dashboard.js"' in html
    assert 'href="https://deerflow.tech"' in html
    assert 'target="_blank"' in html
    assert 'role="tablist"' in html
    assert html.count('role="tab"') == 8
    assert "innerHTML" not in script
    assert "textContent" in script


class NonCompliantRecentSource:
    def __init__(self, records: list[Any]):
        self.records = records

    def recent(self, limit: int = 50) -> list[Any]:
        del limit
        return self.records


def test_snapshot_blocks_secret_key_and_text_variants_with_allowlisted_settings() -> (
    None
):
    raw_settings = {
        "profile": {
            "display_name": "Louis",
            "timezone": "Asia/Shanghai",
            "apiKey": SECRET,
            "private_note": "must not be published",
        },
        "runtime": {
            "enabled_jobs": ["morning_briefing"],
            "coach_mode": "gentle",
            "webhook_url": WEBHOOK,
            "access_key": "access-secret-value",
        },
        "llm": {
            "provider": "deepseek",
            "simple_model": "v4flash",
            "complex_model": "v4pro",
            "key": "plain-key-secret",
            "apiKey": SECRET,
            "internal_prompt": "private system prompt",
        },
        "tools": {
            "github": {
                "enabled": True,
                "allowed_operations": ["read"],
                "access_key": "tool-access-secret",
            }
        },
        "mcp": {
            "research": {
                "enabled": True,
                "transport": "stdio",
                "command": ["private-command"],
            }
        },
        "automations": {
            "status": {
                "enabled": True,
                "type": "status_report",
                "policy": "ask",
                "argv": ["private-command"],
            }
        },
        "arbitrary": {"raw": "must never be recursively published"},
    }
    notices = RecentSource(
        [
            {
                "id": "secret-patterns",
                "kind": "morning_briefing",
                "title": "Credential check",
                "body": (
                    "password: hunter2 prefix(sk-embedded-secret-123456789),suffix "
                    "see=<https://hooks.example.test/private?q=token>,now "
                    "apiKey: camel-secret access_key=snake-secret key: plain-secret"
                ),
                "created_at": "2026-07-27T08:00:00+00:00",
                "status": "delivered",
            }
        ]
    )

    result = make_snapshot(settings=lambda: raw_settings, notifications=notices).build()
    public_settings = result["sections"]["settings"]["data"]
    serialized = json.dumps(result, ensure_ascii=False)

    assert set(public_settings) == {
        "profile",
        "runtime",
        "llm",
        "tools",
        "mcp",
        "automations",
    }
    assert public_settings["profile"] == {
        "display_name": "Louis",
        "timezone": "Asia/Shanghai",
    }
    assert public_settings["llm"]["provider"] == "deepseek"
    assert public_settings["llm"]["simple_model"] == "v4flash"
    assert public_settings["tools"]["github"]["enabled"] is True
    assert public_settings["mcp"]["research"]["transport"] == "stdio"
    assert public_settings["automations"]["status"]["policy"] == "ask"
    for forbidden in (
        "hunter2",
        "sk-embedded-secret-123456789",
        "hooks.example.test",
        "camel-secret",
        "snake-secret",
        "plain-secret",
        "plain-key-secret",
        "access-secret-value",
        "private system prompt",
        "private-command",
        "must not be published",
        "must never be recursively published",
    ):
        assert forbidden not in serialized


def test_snapshot_bounds_noncompliant_sources_and_oversized_state() -> None:
    huge = "x" * 100_000
    state = {
        "daily_tasks": [
            {
                "id": f"task-{index}",
                "plan_date": "2026-07-27",
                "title": huge,
                "status": "pending",
                "priority": index,
            }
            for index in range(1_000)
        ],
        "goals": [
            {
                "id": f"goal-{index}",
                "title": huge,
                "description": huge,
                "status": "active",
                "created_at": "2026-07-01T00:00:00+00:00",
            }
            for index in range(1_000)
        ],
        "memories": [memory(f"memory-{index}", huge) for index in range(1_000)],
    }
    records = [
        {
            "at": "2026-07-27T08:00:00+00:00",
            "tool": "filesystem",
            "operation": huge,
            "status": "ok",
        }
        for _ in range(1_000)
    ]

    result = make_snapshot(
        state_source=lambda: state,
        tool_audit=NonCompliantRecentSource(records),
        recent_limit=30,
    ).build()

    assert len(result["sections"]["today"]["data"]["tasks"]) <= 100
    assert len(result["sections"]["goals"]["data"]["items"]) <= 100
    assert len(result["sections"]["memory"]["data"]["items"]) <= 100
    assert len(result["sections"]["activity"]["data"]["tools"]) <= 30
    assert len(result["sections"]["activity"]["data"]["tools"][0]["operation"]) <= 2_000
    assert len(json.dumps(result)) < 900_000


def test_today_uses_user_timezone_and_exposes_complete_daily_context() -> None:
    local_state = state_payload()
    local_state["daily_tasks"].append(
        {
            "id": "task-local-day",
            "plan_date": "2026-07-28",
            "title": "Local Tuesday task",
            "status": "pending",
            "priority": 1,
        }
    )
    notifications = RecentSource(
        [
            {
                "id": "brief",
                "kind": "morning_briefing",
                "title": "Morning briefing",
                "body": "Briefing body",
                "created_at": "2026-07-27T23:50:00+00:00",
                "status": "delivered",
            },
            {
                "id": "review",
                "kind": "evening_review",
                "title": "Evening review",
                "body": "Review body",
                "created_at": "2026-07-27T23:55:00+00:00",
                "status": "delivered",
            },
            {
                "id": "reminder",
                "kind": "stale_goal_reminders",
                "title": "Proactive reminders",
                "body": "Check Nexus goal",
                "created_at": "2026-07-27T23:58:00+00:00",
                "status": "delivered",
            },
        ]
    )
    local_now = datetime(2026, 7, 27, 16, 30, tzinfo=UTC)

    result = make_snapshot(
        state_source=lambda: local_state,
        notifications=notifications,
        clock=lambda: local_now,
        timezone="Asia/Shanghai",
    ).build()
    today = result["sections"]["today"]["data"]

    assert today["date"] == "2026-07-28"
    assert [task["id"] for task in today["tasks"]] == ["task-local-day"]
    assert today["latest_briefing"]["id"] == "brief"
    assert today["latest_review"]["id"] == "review"
    assert [item["id"] for item in today["reminders"]] == ["reminder"]
    assert today["scheduled_jobs"] == [
        {
            "name": "morning_briefing",
            "enabled": True,
            "time": "08:00",
            "next_occurrence": "2026-07-28T08:00:00+00:00",
        }
    ]


def test_snapshot_rejects_invalid_timezone() -> None:
    with pytest.raises(ValueError, match="timezone"):
        make_snapshot(timezone="Mars/Olympus")


def _request_status(
    server: DashboardServer,
    path: str,
    headers: dict[str, str] | None = None,
) -> int:
    import http.client

    connection = http.client.HTTPConnection(server.host, server.port, timeout=3)
    try:
        connection.request("GET", path, headers=headers or {})
        response = connection.getresponse()
        response.read()
        return response.status
    finally:
        connection.close()


def test_server_rejects_host_header_and_foreign_origin() -> None:
    with DashboardServer(make_snapshot(), port=0) as server:
        assert _request_status(server, "/api/snapshot") == 200
        assert (
            _request_status(
                server,
                "/api/snapshot",
                {"Origin": server.url},
            )
            == 200
        )
        assert (
            _request_status(
                server,
                "/api/snapshot",
                {"Host": f"evil.example:{server.port}"},
            )
            == 403
        )
        assert (
            _request_status(
                server,
                "/api/snapshot",
                {"Origin": "https://evil.example"},
            )
            == 403
        )


@pytest.mark.parametrize(
    "path",
    ["/api/snapshot?x=1", "/api/snapshot#fragment", "/%61pi/snapshot"],
)
def test_server_rejects_non_exact_route_aliases(path: str) -> None:
    with DashboardServer(make_snapshot(), port=0) as server:
        assert _request_status(server, path) == 404


def test_frontend_renders_complete_today_contract() -> None:
    script = (
        Path(__file__).parents[1] / "src" / "nexus" / "dashboard" / "dashboard.js"
    ).read_text(encoding="utf-8")

    assert "scheduled_jobs" in script
    assert "latest_briefing" in script
    assert "latest_review" in script
    assert "reminders" in script


def test_built_wheel_and_sdist_include_dashboard_assets(tmp_path: Path) -> None:
    import shutil

    root = Path(__file__).parents[1]
    project = tmp_path / "project"
    project.mkdir()
    shutil.copy2(root / "pyproject.toml", project / "pyproject.toml")
    for readme in ("README.md", "README_zh.md"):
        shutil.copy2(root / readme, project / readme)
    shutil.copytree(
        root / "src",
        project / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
    )
    wheel_dir = tmp_path / "wheel"
    sdist_dir = tmp_path / "sdist"
    script = (
        "from setuptools.build_meta import build_sdist, build_wheel; "
        f"print(build_wheel({str(wheel_dir)!r})); "
        f"print(build_sdist({str(sdist_dir)!r}))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    wheel = next(wheel_dir.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        wheel_names = set(archive.namelist())
    expected = {
        "nexus/dashboard/index.html",
        "nexus/dashboard/dashboard.css",
        "nexus/dashboard/dashboard.js",
    }
    assert expected <= wheel_names

    sdist = next(sdist_dir.glob("*.tar.gz"))
    with tarfile.open(sdist, "r:gz") as archive:
        sdist_names = {name.split("/", 1)[-1] for name in archive.getnames()}
    assert {f"src/{name}" for name in expected} <= sdist_names


class SliceOnlyList(list[Any]):
    def __iter__(self):
        raise AssertionError("raw memory collection was traversed before bounding")


def test_memory_is_allowlisted_and_bounded_before_lifecycle_normalization() -> None:
    oversized_tags = SliceOnlyList([f"tag-{index}" for index in range(10_000)])
    oversized_conflicts = SliceOnlyList(
        [f"conflict-{index}" for index in range(10_000)]
    )
    oversized_summaries = SliceOnlyList([f"summary-{index}" for index in range(10_000)])
    unknown_collection = SliceOnlyList(["private"] * 10_000)
    raw = memory("bounded-memory", "m" * 100_000)
    raw.update(
        {
            "tags": oversized_tags,
            "conflicts_with": oversized_conflicts,
            "summary_of": oversized_summaries,
            "unknown_collection": unknown_collection,
        }
    )
    malformed = memory("malformed-memory", "Malformed memory")
    malformed["tags"] = {"unexpected": "mapping"}
    whitespace_prefixed = memory(
        "whitespace-prefixed",
        " " * 100_000 + "must not be scanned before bounding",
    )

    result = make_snapshot(
        state_source=lambda: {
            "daily_tasks": [],
            "goals": [],
            "memories": [raw, malformed, whitespace_prefixed],
        }
    ).build()

    section = result["sections"]["memory"]
    assert section["status"] == "ok"
    assert section["error"] is None
    assert [item["id"] for item in section["data"]["items"]] == ["bounded-memory"]
    item = section["data"]["items"][0]
    assert len(item["text"]) <= 1_000
    assert len(item["tags"]) <= 100
    assert "unknown_collection" not in json.dumps(result)
