from __future__ import annotations

from datetime import UTC, datetime
from time import monotonic
from typing import Any
from uuid import uuid4

from nexus.service import NexusService, isoformat

from .models import (
    AgentBudget,
    AgentBudgetExceeded,
    AgentResult,
    AgentRunContext,
    AgentRunTrace,
    AgentStepTrace,
)
from .specialists import CoachAgent, MemoryAgent, PlannerAgent, ReflectionAgent
from .tool_agent import ToolAgent
from .trace import AgentTraceStore, sanitize_trace_data


class AgentOrchestrator:
    def __init__(
        self,
        service: NexusService,
        *,
        mcp_manager: Any,
        trace_store: AgentTraceStore,
        agents: dict[str, Any] | None = None,
        raise_agent_errors: bool = False,
    ):
        self.service = service
        self.trace_store = trace_store
        self.raise_agent_errors = raise_agent_errors
        defaults = {
            "memory": MemoryAgent(service),
            "tool": ToolAgent(mcp_manager, llm=service.llm),
            "planner": PlannerAgent(service),
            "reflection": ReflectionAgent(service),
            "coach": CoachAgent(service),
        }
        defaults.update(agents or {})
        self.agents = defaults

    def run_plan(
        self,
        *,
        user_name: str = "User",
        now: datetime | None = None,
        coach_mode: str = "gentle",
        use_llm: bool = False,
        mcp_context: dict[str, Any] | None = None,
        budget: AgentBudget | None = None,
    ) -> dict[str, Any]:
        return self._run(
            "plan",
            user_name,
            coach_mode,
            use_llm,
            {
                "now": now,
                "mcp_context": mcp_context or {"results": [], "errors": []},
            },
            budget,
        )

    def run_review(
        self,
        *,
        user_name: str = "User",
        now: datetime | None = None,
        coach_mode: str = "gentle",
        use_llm: bool = False,
        budget: AgentBudget | None = None,
    ) -> dict[str, Any]:
        return self._run(
            "review",
            user_name,
            coach_mode,
            use_llm,
            {"now": now},
            budget,
        )

    def run_briefing(
        self,
        *,
        user_name: str = "User",
        weather: str | None = None,
        now: datetime | None = None,
        use_llm: bool = False,
        external_context: dict[str, Any] | None = None,
        budget: AgentBudget | None = None,
    ) -> dict[str, Any]:
        return self._run(
            "briefing",
            user_name,
            "gentle",
            use_llm,
            {
                "now": now,
                "weather": weather,
                "external_context": external_context,
            },
            budget,
        )

    def _run(
        self,
        workflow: str,
        user_name: str,
        coach_mode: str,
        use_llm: bool,
        inputs: dict[str, Any],
        budget: AgentBudget | None,
    ) -> dict[str, Any]:
        started = monotonic()
        started_at = datetime.now(UTC)
        run_id = uuid4().hex[:12]
        inputs["goals"] = self.service.list_goals()
        inputs["query"] = self._query(workflow, user_name, inputs["goals"])
        context = AgentRunContext(
            run_id=run_id,
            workflow=workflow,
            user_name=user_name,
            coach_mode=coach_mode,
            started_at=isoformat(started_at),
            budget=budget or AgentBudget(),
            inputs=inputs,
            use_llm=use_llm,
        )
        order = (
            ["memory", "reflection", "coach"]
            if workflow == "review"
            else ["memory", "tool", "planner", "coach"]
        )
        steps: list[AgentStepTrace] = []
        for agent_name in order:
            if not self._run_step(agent_name, context, steps):
                break

        response = self._best_response(context)
        had_degradation = len(steps) < len(order) or any(
            step.status != "completed" for step in steps
        )
        status = "partial" if had_degradation else "completed"
        completed_at = datetime.now(UTC)
        duration_ms = int((monotonic() - started) * 1000)
        trace = AgentRunTrace(
            run_id=run_id,
            workflow=workflow,
            user_name=user_name,
            started_at=isoformat(started_at),
            completed_at=isoformat(completed_at),
            status=status,
            duration_ms=duration_ms,
            steps=steps,
            budget=context.budget.to_dict(),
        )
        self.trace_store.append(trace)
        response["agents"] = {
            "used": True,
            "run_id": run_id,
            "status": status,
            "steps": [sanitize_trace_data(step.to_dict()) for step in steps],
            "budget": context.budget.to_dict(),
        }
        return response

    def _run_step(
        self,
        agent_name: str,
        context: AgentRunContext,
        steps: list[AgentStepTrace],
    ) -> bool:
        started = monotonic()
        try:
            context.budget.consume_step()
        except AgentBudgetExceeded as exc:
            steps.append(
                AgentStepTrace(
                    agent=agent_name,
                    status="skipped",
                    duration_ms=0,
                    summary="Skipped because the shared agent budget was exhausted.",
                    error=str(exc),
                )
            )
            return False
        try:
            result: AgentResult = self.agents[agent_name].run(context)
            context.budget.check_time()
            context.artifacts[agent_name] = result.artifact
            steps.append(
                AgentStepTrace(
                    agent=result.agent,
                    status=result.status,
                    duration_ms=int((monotonic() - started) * 1000),
                    summary=result.summary,
                    metadata=result.metadata,
                    error="recoverable_agent_error" if result.error else None,
                )
            )
        except AgentBudgetExceeded:
            steps.append(
                AgentStepTrace(
                    agent=agent_name,
                    status="failed",
                    duration_ms=int((monotonic() - started) * 1000),
                    summary=f"{agent_name.title()} Agent exceeded the shared deadline.",
                    error="time_budget_exceeded",
                )
            )
        except Exception as exc:
            if self.raise_agent_errors:
                raise
            steps.append(
                AgentStepTrace(
                    agent=agent_name,
                    status="failed",
                    duration_ms=int((monotonic() - started) * 1000),
                    summary=f"{agent_name.title()} Agent failed; local fallback remains available.",
                    error=type(exc).__name__,
                )
            )
        return True

    def _best_response(self, context: AgentRunContext) -> dict[str, Any]:
        memory_context = context.artifacts.get("memory") or self._local_memory_context()
        coach = context.artifacts.get("coach")
        if coach and isinstance(coach.get("response"), dict):
            return coach["response"]
        source_name = "reflection" if context.workflow == "review" else "planner"
        source = context.artifacts.get(source_name)
        if source and isinstance(source.get("response"), dict):
            return source["response"]

        if context.workflow == "review":
            return self.service.daily_review(
                user_name=context.user_name,
                now=context.inputs.get("now"),
                use_llm=False,
                coach_mode=context.coach_mode,
                memory_context=memory_context,
            )
        if context.workflow == "briefing":
            return self.service.daily_briefing(
                user_name=context.user_name,
                weather=context.inputs.get("weather"),
                now=context.inputs.get("now"),
                use_llm=False,
                external_context=context.inputs.get("external_context"),
                memory_context=memory_context,
                mcp_context=context.artifacts.get("tool"),
            )
        return self.service.daily_plan(
            user_name=context.user_name,
            now=context.inputs.get("now"),
            coach_mode=context.coach_mode,
            use_llm=False,
            mcp_context=context.artifacts.get(
                "tool", context.inputs.get("mcp_context")
            ),
            memory_context=memory_context,
        )

    def _local_memory_context(self) -> dict[str, Any]:
        return {
            "memories": self.service.list_memories()[:8],
            "memory_retrieval": {
                "strategy": "recent_memory_fallback",
                "error_category": "agent_memory_unavailable",
            },
        }

    @staticmethod
    def _query(
        workflow: str,
        user_name: str,
        goals: list[dict[str, Any]],
    ) -> str:
        goal_text = " ".join(
            f"{goal.get('title', '')} {goal.get('description', '')}"
            for goal in goals[:5]
        )
        return f"{user_name} {workflow} {goal_text}".strip()
