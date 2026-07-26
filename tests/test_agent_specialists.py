from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nexus.agents.models import AgentBudget, AgentRunContext
from nexus.agents.specialists import (
    CoachAgent,
    MemoryAgent,
    PlannerAgent,
    ReflectionAgent,
)
from nexus.service import NexusService, isoformat
from nexus.store import JsonStore


class FakeLLM:
    def __init__(self, response: str = "Model-assisted coaching"):
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.response


def test_memory_agent_retrieves_relevant_memories(tmp_path: Path) -> None:
    service = seeded_service(tmp_path)
    context = make_context(
        "plan",
        inputs={"query": "Nexus vector database implementation"},
    )

    result = MemoryAgent(service).run(context)

    assert result.status == "completed"
    assert result.artifact["memories"][0]["text"] == "Build Nexus vector database"
    assert "query" not in result.metadata
    assert "strategy" in result.metadata


def test_planner_agent_persists_daily_tasks_and_uses_tool_context(
    tmp_path: Path,
) -> None:
    service = seeded_service(tmp_path)
    context = make_context(
        "plan",
        inputs={"now": datetime(2026, 7, 26, 8, 0, tzinfo=UTC)},
    )
    context.artifacts["memory"] = {"memories": [], "memory_retrieval": {}}
    context.artifacts["tool"] = {
        "results": [
            {
                "server": "calendar",
                "tool": "today",
                "text": ["Meeting at 14:00"],
                "structured_data": None,
            }
        ],
        "errors": [],
    }

    result = PlannerAgent(service).run(context)

    assert result.status == "completed"
    assert len(result.artifact["response"]["tasks"]) == 1
    assert "calendar/today" in result.artifact["response"]["plan"]
    assert len(service.list_daily_tasks("2026-07-26")) == 1


def test_briefing_planner_uses_memory_and_mcp_artifacts(tmp_path: Path) -> None:
    service = seeded_service(tmp_path)
    context = make_context(
        "briefing",
        inputs={"now": datetime(2026, 7, 26, 8, 0, tzinfo=UTC)},
    )
    context.artifacts["memory"] = {
        "memories": [{"text": "Use retrieved agent memory", "tags": []}],
        "memory_retrieval": {"strategy": "agent_test"},
    }
    context.artifacts["tool"] = {
        "results": [
            {
                "server": "research",
                "tool": "search",
                "text": ["New multi-agent paper"],
                "structured_data": None,
            }
        ],
        "errors": [],
    }

    result = PlannerAgent(service).run(context)

    response = result.artifact["response"]
    assert response["relevant_memories"][0]["text"] == "Use retrieved agent memory"
    assert "research/search" in response["briefing"]


def test_reflection_agent_returns_structured_outcomes(tmp_path: Path) -> None:
    service = seeded_service(tmp_path)
    now = datetime(2026, 7, 26, 20, 0, tzinfo=UTC)
    plan = service.daily_plan(now=now)
    service.update_daily_task(
        plan["tasks"][0]["id"],
        blocker="Need benchmark data",
        unresolved=["Collect benchmark"],
        now=now,
    )
    context = make_context("review", inputs={"now": now})

    result = ReflectionAgent(service).run(context)

    response = result.artifact["response"]
    assert response["blocked_tasks"][0]["blocker"] == "Need benchmark data"
    assert response["unresolved_tasks"][0]["item"] == "Collect benchmark"
    assert response["tomorrow_priorities"]


def test_coach_agent_applies_each_mode_without_llm(tmp_path: Path) -> None:
    service = seeded_service(tmp_path)
    for mode in ("strict", "gentle", "academic", "startup"):
        context = make_context("plan", coach_mode=mode)
        context.artifacts["planner"] = {"response": {"plan": "Base plan", "tasks": []}}

        result = CoachAgent(service).run(context)

        assert result.status == "completed"
        assert mode in result.artifact["response"]["plan"].lower()
        assert context.budget.used_llm_calls == 0


def test_coach_agent_uses_one_budgeted_llm_call(tmp_path: Path) -> None:
    llm = FakeLLM()
    service = seeded_service(tmp_path, llm=llm)
    context = make_context("plan", use_llm=True)
    context.artifacts["planner"] = {
        "response": {
            "plan": "Base plan",
            "tasks": [{"title": "Ship agent MVP"}],
            "relevant_memories": [{"text": "Private memory"}],
        }
    }

    result = CoachAgent(service).run(context)

    assert result.artifact["response"]["plan"] == "Model-assisted coaching"
    assert result.artifact["response"]["llm"]["used"] is True
    assert context.budget.used_llm_calls == 1
    assert len(llm.calls) == 1


def seeded_service(tmp_path: Path, llm: FakeLLM | None = None) -> NexusService:
    service = NexusService(JsonStore(tmp_path / "state.json"), llm=llm)
    service.add_memory("Build Nexus vector database", ["nexus", "rag"])
    service.add_memory("Practice IELTS listening", ["ielts"])
    service.add_goal("Finish Phase 8", "Implement multi-agent coordination", 3)
    return service


def make_context(
    workflow: str,
    *,
    coach_mode: str = "gentle",
    inputs: dict[str, object] | None = None,
    use_llm: bool = False,
) -> AgentRunContext:
    now = datetime(2026, 7, 26, 8, 0, tzinfo=UTC)
    return AgentRunContext(
        run_id="run-test",
        workflow=workflow,
        user_name="User",
        coach_mode=coach_mode,
        started_at=isoformat(now),
        budget=AgentBudget(),
        inputs=dict(inputs or {}),
        use_llm=use_llm,
    )
