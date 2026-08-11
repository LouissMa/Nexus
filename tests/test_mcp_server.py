from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from nexus.mcp.models import MCPPermissionError, MCPToolError
from nexus.mcp_server import NexusMCPTools
from nexus.service import NexusService
from nexus.store import JsonStore


NOW = datetime(2026, 8, 8, 9, 0, tzinfo=UTC)


def make_tools(
    tmp_path: Path, *, policies: dict[str, str] | None = None
) -> NexusMCPTools:
    service = NexusService(JsonStore(tmp_path / "state.json"))
    service.add_goal("Build Nexus", "Personal AI workspace", 3)
    service.add_memory(
        "Louis is researching personal AI systems", ["research"], now=NOW
    )
    return NexusMCPTools(service, policies=policies, clock=lambda: NOW)


def test_catalog_is_static_bounded_and_has_exact_schemas(tmp_path: Path) -> None:
    catalog = make_tools(tmp_path).list_tools()
    assert [item["name"] for item in catalog] == [
        "nexus_today",
        "nexus_search_memory",
        "nexus_list_goals",
        "nexus_list_habits",
        "nexus_list_projects",
        "nexus_get_suggestions",
        "nexus_preview_replan",
        "nexus_add_memory",
        "nexus_add_goal",
        "nexus_check_in_habit",
        "nexus_update_project_progress",
        "nexus_apply_replan",
    ]
    assert catalog[1]["inputSchema"]["required"] == ["query"]
    assert catalog[7]["permission"] == "ask"


def test_read_tools_validate_arguments_and_return_bounded_data(tmp_path: Path) -> None:
    tools = make_tools(tmp_path)
    goals = tools.call("nexus_list_goals", {})
    memories = tools.call("nexus_search_memory", {"query": "AI research", "limit": 3})
    assert goals["items"][0]["title"] == "Build Nexus"
    assert memories["items"][0]["text"].startswith("Louis")
    with pytest.raises(MCPToolError, match="arguments"):
        tools.call("nexus_search_memory", {"query": "x", "unknown": True})
    with pytest.raises(MCPToolError, match="limit"):
        tools.call("nexus_search_memory", {"query": "x", "limit": 100})


def test_date_formats_are_enforced(tmp_path: Path) -> None:
    with pytest.raises(MCPToolError, match="date"):
        make_tools(tmp_path).call("nexus_today", {"date": "08/08/2026"})


def test_memory_goal_and_replan_tools_follow_read_write_permissions(
    tmp_path: Path,
) -> None:
    tools = make_tools(tmp_path)
    preview = tools.call(
        "nexus_preview_replan",
        {"date": "2026-08-08", "events": []},
    )
    assert preview["plan_date"] == "2026-08-08"

    with pytest.raises(MCPPermissionError, match="approval"):
        tools.call("nexus_add_memory", {"text": "Prefer focused mornings"})
    memory = tools.call(
        "nexus_add_memory",
        {"text": "Prefer focused mornings", "tags": ["preference"]},
        session_approvals=("nexus_add_memory",),
    )
    goal = tools.call(
        "nexus_add_goal",
        {"title": "Publish Nexus", "description": "Ship the next release"},
        session_approvals=("nexus_add_goal",),
    )
    assert memory["text"] == "Prefer focused mornings"
    assert goal["title"] == "Publish Nexus"


def test_mutations_obey_deny_ask_allow_and_session_approval(tmp_path: Path) -> None:
    service = NexusService(JsonStore(tmp_path / "state.json"))
    habit = service.add_habit("Journal", "", "daily", (), 1, None, now=NOW)
    ask = NexusMCPTools(service, clock=lambda: NOW)
    arguments = {"habit_id": habit["id"], "date": "2026-08-08", "count": 1}
    with pytest.raises(MCPPermissionError, match="approval"):
        ask.call("nexus_check_in_habit", arguments)
    result = ask.call(
        "nexus_check_in_habit",
        arguments,
        session_approvals=("nexus_check_in_habit",),
    )
    assert result["summary"]["today_complete"] is True

    denied = NexusMCPTools(service, policies={"nexus_check_in_habit": "deny"})
    with pytest.raises(MCPPermissionError, match="denied"):
        denied.call(
            "nexus_check_in_habit",
            arguments,
            session_approvals=("nexus_check_in_habit",),
        )


def test_unknown_tools_and_sensitive_audit_values_are_safe(tmp_path: Path) -> None:
    tools = make_tools(tmp_path)
    tools.audit.path = tmp_path / "audit.jsonl"
    with pytest.raises(MCPToolError, match="Unknown"):
        tools.call("missing", {"api_key": "secret-value"})
    event = tools.audit.recent(1)[0]
    assert "secret-value" not in str(event)
    assert event["arguments"]["count"] == 1


def test_audit_never_records_raw_user_content(tmp_path: Path) -> None:
    tools = make_tools(tmp_path)
    tools.audit.path = tmp_path / "audit.jsonl"
    tools.call(
        "nexus_search_memory",
        {"query": "private research question", "task_context": "private note"},
    )
    serialized = json.dumps(tools.audit.recent(1)[0])
    assert "private research question" not in serialized
    assert "private note" not in serialized


def test_oversized_arguments_are_rejected_with_bounded_audit(tmp_path: Path) -> None:
    tools = make_tools(tmp_path)
    tools.audit.path = tmp_path / "audit.jsonl"

    with pytest.raises(MCPToolError, match="size limit"):
        tools.call("nexus_search_memory", {"query": "x" * 20_000})

    assert tools.audit.path.stat().st_size < 8_192


def test_oversized_service_results_are_replaced_by_bounded_summary(
    tmp_path: Path,
) -> None:
    tools = make_tools(tmp_path)
    tools.service.list_goals = lambda: [{"title": "x" * 10_000} for _ in range(100)]

    result = tools.call("nexus_list_goals", {})

    assert len(json.dumps(result).encode("utf-8")) <= 65_536
    assert result["truncated"] is True
