from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.agents.models import AgentBudget, AgentRunContext
from nexus.agents.tool_agent import ToolAgent
from nexus.mcp.audit import MCPAuditLogger
from nexus.mcp.manager import MCPManager
from nexus.mcp.models import MCPCallResult, MCPToolSchema


class FakeGateway:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.discover_timeouts: list[float] = []
        self.call_timeouts: list[float] = []

    def list_tools(self, server: dict[str, object]) -> list[MCPToolSchema]:
        self.discover_timeouts.append(float(server["timeout_seconds"]))
        return [
            MCPToolSchema(
                name="search",
                title="Search",
                description="Search research sources",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            ),
            MCPToolSchema(
                name="delete",
                title="Delete",
                description="Delete a record",
                input_schema={"type": "object"},
            ),
        ]

    def call_tool(
        self,
        server: dict[str, object],
        tool: str,
        arguments: dict[str, object],
    ) -> MCPCallResult:
        self.calls.append((tool, arguments))
        self.call_timeouts.append(float(server["timeout_seconds"]))
        return MCPCallResult(
            tool=tool,
            text=["two papers found"],
            structured_data={"count": 2},
        )


class FakeLLM:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        return self.response


def test_manager_agent_candidates_include_only_allow_policy_tools(
    tmp_path: Path,
) -> None:
    manager, _ = build_manager(tmp_path)

    candidates = manager.agent_candidates()

    assert [(item["server"], item["tool"]) for item in candidates["tools"]] == [
        ("research", "search")
    ]
    assert candidates["tools"][0]["bound_arguments"] == {"query": "Nexus agents"}
    assert candidates["errors"] == []


def test_tool_agent_calls_deterministic_allowed_bindings(tmp_path: Path) -> None:
    manager, gateway = build_manager(tmp_path)
    context = make_context()

    result = ToolAgent(manager).run(context)

    assert result.status == "completed"
    assert gateway.calls == [("search", {"query": "Nexus agents"})]
    assert result.artifact["results"][0]["server"] == "research"
    assert result.metadata["selected_tools"] == [
        {
            "server": "research",
            "tool": "search",
            "argument_keys": ["query"],
        }
    ]
    assert context.budget.used_tool_calls == 1
    assert "Nexus agents" not in json.dumps(result.metadata)


def test_tool_agent_clamps_mcp_timeouts_to_remaining_run_deadline(
    tmp_path: Path,
) -> None:
    manager, gateway = build_manager(tmp_path)
    context = make_context()
    context.budget.max_seconds = 7

    ToolAgent(manager).run(context)

    assert 0 < gateway.discover_timeouts[0] <= 7
    assert 0 < gateway.call_timeouts[0] <= 7


def test_tool_agent_uses_strict_llm_selection_for_unbound_allow_tool(
    tmp_path: Path,
) -> None:
    manager, gateway = build_manager(tmp_path, planning_tools=[])
    llm = FakeLLM(
        '{"calls":[{"server":"research","tool":"search",'
        '"arguments":{"query":"multi-agent systems"}}]}'
    )
    context = make_context(use_llm=True)

    result = ToolAgent(manager, llm=llm).run(context)

    assert result.status == "completed"
    assert gateway.calls == [("search", {"query": "multi-agent systems"})]
    assert llm.calls == 1
    assert context.budget.used_llm_calls == 1
    assert context.budget.used_tool_calls == 1


def test_tool_agent_rejects_invented_or_schema_invalid_llm_calls(
    tmp_path: Path,
) -> None:
    manager, gateway = build_manager(tmp_path, planning_tools=[])
    for response in (
        '{"calls":[{"server":"research","tool":"delete","arguments":{}}]}',
        '{"calls":[{"server":"research","tool":"search","arguments":{}}]}',
        "not json",
    ):
        context = make_context(use_llm=True)
        result = ToolAgent(manager, llm=FakeLLM(response)).run(context)

        assert result.status == "fallback"
        assert result.artifact["results"] == []
        assert result.artifact["errors"]
    assert gateway.calls == []


def test_tool_agent_validates_deterministic_binding_before_call(tmp_path: Path) -> None:
    manager, gateway = build_manager(
        tmp_path,
        planning_tools=[{"tool": "search", "arguments": {"unexpected": True}}],
    )

    result = ToolAgent(manager).run(make_context())

    assert result.status == "fallback"
    assert gateway.calls == []
    assert result.artifact["errors"]


def test_tool_agent_stops_at_shared_tool_budget(tmp_path: Path) -> None:
    manager, gateway = build_manager(
        tmp_path,
        planning_tools=[
            {"tool": "search", "arguments": {"query": "one"}},
            {"tool": "search", "arguments": {"query": "two"}},
        ],
    )
    context = make_context()
    context.budget.max_tool_calls = 1

    result = ToolAgent(manager).run(context)

    assert gateway.calls == [("search", {"query": "one"})]
    assert result.status == "partial"
    assert "budget" in result.artifact["errors"][0]["error"].lower()


def test_tool_agent_applies_complete_json_schema_validation() -> None:
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 3},
            "limit": {"type": "integer", "maximum": 5},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    with pytest.raises(ValueError, match="schema"):
        ToolAgent._validate_arguments({"query": "x", "unexpected": True}, schema)


def build_manager(
    tmp_path: Path,
    *,
    planning_tools: list[dict[str, object]] | None = None,
) -> tuple[MCPManager, FakeGateway]:
    gateway = FakeGateway()
    server = {
        "enabled": True,
        "transport": "stdio",
        "command": "python",
        "args": ["server.py"],
        "env": {},
        "timeout_seconds": 10,
        "max_retries": 0,
        "tool_policies": {"search": "allow", "delete": "ask"},
        "planning_tools": (
            [{"tool": "search", "arguments": {"query": "Nexus agents"}}]
            if planning_tools is None
            else planning_tools
        ),
    }
    return (
        MCPManager(
            {"research": server},
            gateway,
            MCPAuditLogger(tmp_path / "mcp_audit.jsonl"),
        ),
        gateway,
    )


def make_context(*, use_llm: bool = False) -> AgentRunContext:
    now = datetime(2026, 7, 26, 8, 0, tzinfo=UTC)
    return AgentRunContext(
        run_id="run-tool",
        workflow="plan",
        user_name="User",
        coach_mode="gentle",
        started_at=now.isoformat(),
        budget=AgentBudget(),
        inputs={"query": "Plan Nexus multi-agent implementation"},
        use_llm=use_llm,
    )
