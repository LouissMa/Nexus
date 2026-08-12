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
                "source_types": ["habit", "memory"],
                "context": {
                    "calendar": "unavailable",
                    "rag": "available",
                    "degradations": ["calendar_unavailable"],
                },
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
    assert suggestion["source_types"] == ["habit", "memory"]
    assert suggestion["context"] == {
        "calendar": "unavailable",
        "rag": "available",
        "degradations": ["calendar_unavailable"],
    }
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


def test_replan_reads_calendar_server_side_for_preview_and_apply(
    tmp_path: Path,
) -> None:
    service = NexusService(JsonStore(tmp_path / "state.json"))
    calls: list[str] = []

    def calendar_events(plan_date: str) -> list[dict]:
        calls.append(plan_date)
        return [
            {
                "summary": "Research meeting",
                "start": f"{plan_date}T09:00:00+00:00",
                "end": f"{plan_date}T10:00:00+00:00",
                "all_day": False,
            }
        ]

    actions = DashboardActions(
        service,
        timezone="UTC",
        clock=lambda: NOW,
        calendar_events=calendar_events,
    )
    preview = actions.dispatch(
        "/api/replan/preview",
        {"date": "2026-08-08", "working_start": "09:00", "working_end": "18:00"},
    )
    result = actions.dispatch("/api/replan/apply", {"preview": preview})

    assert calls == ["2026-08-08", "2026-08-08"]
    assert preview["degradations"] == []
    assert result["preview_id"] == preview["id"]


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

        service.check_in_habit(
            habit_id, "2026-08-08", 2, "other client", timezone="UTC", now=NOW
        )
        status, result = post(
            server,
            f"/api/habits/{habit_id}/check-in",
            {"date": "2026-08-08", "increment": 1},
        )
        assert status == 200
        assert result["result"]["summary"]["today_count"] == 3

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
