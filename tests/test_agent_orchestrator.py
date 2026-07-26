from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.agents.models import AgentBudget
from nexus.agents.orchestrator import AgentOrchestrator
from nexus.agents.trace import AgentTraceStore
from nexus.mcp.audit import MCPAuditLogger
from nexus.mcp.manager import MCPManager
from nexus.service import NexusService
from nexus.store import JsonStore
from nexus.vector_store import VectorStoreError


class EmptyGateway:
    def list_tools(self, server: dict[str, object]) -> list[object]:
        return []

    def call_tool(
        self,
        server: dict[str, object],
        tool: str,
        arguments: dict[str, object],
    ) -> object:
        raise AssertionError("No tool calls expected.")


class FailingRetriever:
    def retrieve_result(self, memories: list[dict], query: str, limit: int) -> object:
        raise VectorStoreError("vector backend private failure")


class BuggyRetriever:
    def retrieve_result(self, memories: list[dict], query: str, limit: int) -> object:
        raise KeyError("retriever programming bug")


class AdvancingAgent:
    name = "memory"

    def __init__(self, clock_state: list[float]):
        self.clock_state = clock_state

    def run(self, context: object) -> object:
        self.clock_state[0] = 61.0
        from nexus.agents.models import AgentResult

        return AgentResult("memory", "completed", "Slow result", artifact={})


class BuggyAgent:
    name = "memory"

    def run(self, context: object) -> object:
        raise KeyError("programming bug")


class FailingAgent:
    name = "memory"

    def run(self, context: object) -> object:
        raise RuntimeError("private backend details")


def test_plan_workflow_runs_agents_in_order_and_persists_tasks(
    tmp_path: Path,
) -> None:
    orchestrator, service, traces = build_orchestrator(tmp_path)
    now = datetime(2026, 7, 26, 8, 0, tzinfo=UTC)

    response = orchestrator.run_plan(
        user_name="User",
        now=now,
        coach_mode="startup",
    )

    assert [step["agent"] for step in response["agents"]["steps"]] == [
        "memory",
        "tool",
        "planner",
        "coach",
    ]
    assert response["agents"]["status"] == "completed"
    assert response["tasks"]
    assert service.list_daily_tasks("2026-07-26") == response["tasks"]
    assert traces.find(response["agents"]["run_id"]) is not None


def test_review_and_briefing_workflows_return_existing_response_shapes(
    tmp_path: Path,
) -> None:
    orchestrator, _, _ = build_orchestrator(tmp_path)
    now = datetime(2026, 7, 26, 20, 0, tzinfo=UTC)

    review = orchestrator.run_review(user_name="User", now=now)
    briefing = orchestrator.run_briefing(
        user_name="User",
        now=now,
        weather="Sunny, 25 C",
    )

    assert "review" in review
    assert [item["agent"] for item in review["agents"]["steps"]] == [
        "memory",
        "reflection",
        "coach",
    ]
    assert "briefing" in briefing
    assert [item["agent"] for item in briefing["agents"]["steps"]] == [
        "memory",
        "tool",
        "planner",
        "coach",
    ]


def test_agent_failure_is_isolated_and_local_fallback_still_returns_plan(
    tmp_path: Path,
) -> None:
    orchestrator, _, _ = build_orchestrator(
        tmp_path,
        agents={"memory": FailingAgent()},
    )

    response = orchestrator.run_plan(
        user_name="User",
        now=datetime(2026, 7, 26, 8, 0, tzinfo=UTC),
    )

    assert response["tasks"]
    assert response["agents"]["status"] == "partial"
    assert response["agents"]["steps"][0]["status"] == "failed"
    assert "private backend details" not in str(response["agents"]["steps"])


def test_step_budget_exhaustion_returns_local_fallback_and_trace(
    tmp_path: Path,
) -> None:
    orchestrator, _, traces = build_orchestrator(tmp_path)
    budget = AgentBudget(max_steps=2)

    response = orchestrator.run_plan(
        user_name="User",
        now=datetime(2026, 7, 26, 8, 0, tzinfo=UTC),
        budget=budget,
    )

    assert response["tasks"]
    assert response["agents"]["status"] == "partial"
    assert response["agents"]["budget"]["used"]["steps"] == 2
    trace = traces.find(response["agents"]["run_id"])
    assert trace is not None
    assert trace["status"] == "partial"


def test_requested_llm_without_configuration_uses_coach_fallback(
    tmp_path: Path,
) -> None:
    orchestrator, _, _ = build_orchestrator(tmp_path)

    response = orchestrator.run_briefing(
        user_name="User",
        now=datetime(2026, 7, 26, 8, 0, tzinfo=UTC),
        use_llm=True,
    )

    assert response["briefing"]
    assert response["llm"]["used"] is False
    assert response["agents"]["status"] == "partial"


def test_real_rag_failure_uses_recent_memory_fallback_and_records_trace(
    tmp_path: Path,
) -> None:
    orchestrator, service, traces = build_orchestrator(tmp_path)
    service.memory_retriever = FailingRetriever()

    response = orchestrator.run_plan(
        user_name="User",
        now=datetime(2026, 7, 26, 8, 0, tzinfo=UTC),
    )

    assert response["tasks"]
    assert response["relevant_memories"]
    assert response["agents"]["status"] == "partial"
    assert traces.find(response["agents"]["run_id"]) is not None


def test_wall_clock_deadline_is_checked_after_each_agent(tmp_path: Path) -> None:
    clock_state = [0.0]
    budget = AgentBudget(max_seconds=60, clock=lambda: clock_state[0])
    orchestrator, _, _ = build_orchestrator(
        tmp_path,
        agents={"memory": AdvancingAgent(clock_state)},
    )

    response = orchestrator.run_plan(budget=budget)

    assert response["agents"]["status"] == "partial"
    assert response["agents"]["steps"][0]["status"] == "failed"


def test_programming_errors_can_be_raised_in_strict_test_mode(tmp_path: Path) -> None:
    orchestrator, service, traces = build_orchestrator(tmp_path)
    service.memory_retriever = BuggyRetriever()
    strict = AgentOrchestrator(
        service,
        mcp_manager=orchestrator.agents["tool"].manager,
        trace_store=traces,
        raise_agent_errors=True,
    )

    with pytest.raises(KeyError, match="retriever programming bug"):
        strict.run_plan()


def build_orchestrator(
    tmp_path: Path,
    *,
    agents: dict[str, object] | None = None,
) -> tuple[AgentOrchestrator, NexusService, AgentTraceStore]:
    service = NexusService(JsonStore(tmp_path / "state.json"))
    service.add_memory("Finish Nexus multi-agent coordination", ["nexus", "agents"])
    service.add_goal("Finish Phase 8", "Implement and test the orchestrator", 3)
    manager = MCPManager(
        {},
        EmptyGateway(),
        MCPAuditLogger(tmp_path / "mcp_audit.jsonl"),
    )
    traces = AgentTraceStore(tmp_path / "agent_runs.jsonl")
    return (
        AgentOrchestrator(
            service,
            mcp_manager=manager,
            trace_store=traces,
            agents=agents,
        ),
        service,
        traces,
    )
