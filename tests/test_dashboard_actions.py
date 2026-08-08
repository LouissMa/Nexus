from __future__ import annotations

import http.client
import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from nexus.dashboard import DashboardActions, DashboardServer, DashboardSnapshot
from nexus.service import NexusService
from nexus.store import JsonStore


NOW = datetime(2026, 8, 8, 9, 0, tzinfo=UTC)


def test_snapshot_adds_isolated_bounded_life_sections() -> None:
    state = {
        "daily_tasks": [],
        "goals": [],
        "memories": [],
        "habits": [
            {
                "id": "h1",
                "name": "Read",
                "status": "active",
                "cadence": "daily",
                "weekdays": [],
                "target_count": 1,
                "check_ins": [],
                "description": "safe",
            }
        ],
        "projects": [
            {
                "id": "p1",
                "name": "Nexus",
                "description": "safe",
                "status": "active",
                "priority": 1,
                "target_date": "2026-08-20",
                "goal_ids": [],
                "task_ids": [],
                "milestones": [],
                "progress_entries": [],
            }
        ],
        "suggestions": [
            {
                "id": "s1",
                "kind": "habit_risk",
                "title": "Read",
                "reason": "Due today",
                "confidence": 0.8,
                "source_ids": ["habit:h1"],
                "action": {"type": "acknowledge", "secret": "hide"},
                "status": "open",
                "created_at": "2026-08-08T08:00:00+00:00",
                "expires_at": "2026-08-10T08:00:00+00:00",
            }
        ],
    }
    snapshot = DashboardSnapshot(state_source=lambda: state, clock=lambda: NOW).build()
    assert (
        snapshot["sections"]["habits"]["data"]["items"][0]["summary"]["due_today"]
        is True
    )
    assert (
        snapshot["sections"]["projects"]["data"]["items"][0]["summary"][
            "progress_percent"
        ]
        == 0
    )
    suggestion = snapshot["sections"]["suggestions"]["data"]["items"][0]
    assert suggestion["action"] == {"type": "acknowledge"}
    assert "secret" not in json.dumps(snapshot)


def make_server(tmp_path: Path) -> tuple[DashboardServer, NexusService, str]:
    store = JsonStore(tmp_path / "state.json")
    service = NexusService(store)
    habit = service.add_habit("Read", "", "daily", (), 1, None, timezone="UTC", now=NOW)
    snapshot = DashboardSnapshot(state_source=store.load, clock=lambda: NOW)
    server = DashboardServer(
        snapshot, actions=DashboardActions(service, timezone="UTC"), port=0
    )
    return server, service, habit["id"]


def post(
    server: DashboardServer,
    path: str,
    payload: object,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    body = json.dumps(payload).encode()
    request_headers = {
        "Content-Type": "application/json",
        "Origin": server.url,
        "X-Nexus-CSRF": server.csrf_token,
        "Content-Length": str(len(body)),
    }
    request_headers.update(headers or {})
    connection = http.client.HTTPConnection(server.host, server.port, timeout=3)
    try:
        connection.request("POST", path, body=body, headers=request_headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def test_post_routes_require_origin_csrf_json_and_dispatch_exact_action(
    tmp_path: Path,
) -> None:
    server, service, habit_id = make_server(tmp_path)
    with server:
        with urllib.request.urlopen(server.url + "/", timeout=3) as response:
            html = response.read().decode("utf-8")
        assert server.csrf_token in html
        assert "__NEXUS_CSRF_TOKEN__" not in html

        status, result = post(
            server,
            f"/api/habits/{habit_id}/check-in",
            {"date": "2026-08-08", "count": 1, "note": "done"},
        )
        assert status == 200
        assert result["result"]["summary"]["today_complete"] is True
        assert (
            service.list_habits(timezone="UTC", now=NOW)[0]["summary"]["today_complete"]
            is True
        )

        assert (
            post(
                server,
                f"/api/habits/{habit_id}/check-in",
                {},
                headers={"X-Nexus-CSRF": "wrong"},
            )[0]
            == 403
        )
        assert post(server, "/api/mutate", {})[0] == 404


def test_post_rejects_wrong_content_type_missing_origin_and_oversized_body(
    tmp_path: Path,
) -> None:
    server, _service, habit_id = make_server(tmp_path)
    with server:
        path = f"/api/habits/{habit_id}/check-in"
        assert post(server, path, {}, headers={"Content-Type": "text/plain"})[0] == 415
        assert (
            post(server, path, {}, headers={"Origin": "https://evil.example"})[0] == 403
        )

        connection = http.client.HTTPConnection(server.host, server.port, timeout=3)
        try:
            body = b"{" + b"x" * 20_000 + b"}"
            connection.request(
                "POST",
                path,
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Origin": server.url,
                    "X-Nexus-CSRF": server.csrf_token,
                    "Content-Length": str(len(body)),
                },
            )
            response = connection.getresponse()
            response.read()
            assert response.status == 413
        finally:
            connection.close()
