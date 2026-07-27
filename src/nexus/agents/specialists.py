from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from nexus.embeddings import EmbeddingError
from nexus.llm import LLMError, OpenAICompatibleLLM
from nexus.planning import coach_profile
from nexus.vector_store import VectorStoreError

from .models import AgentBudgetExceeded, AgentResult, AgentRunContext

if TYPE_CHECKING:
    from nexus.service import NexusService


class MemoryAgent:
    name = "memory"

    def __init__(self, service: NexusService):
        self.service = service

    def run(self, context: AgentRunContext) -> AgentResult:
        query = str(context.inputs.get("query") or self._default_query(context))
        limit = int(context.inputs.get("memory_limit", 8))
        try:
            retrieved = self.service.retrieve_memories_result(
                query, limit, now=context.inputs.get("now")
            )
            memories = retrieved.get("results", [])
            retrieval = retrieved.get("memory_retrieval", {})
            status = "completed"
            error = None
        except (EmbeddingError, VectorStoreError):
            memories = self.service.list_memories(now=context.inputs.get("now"))[:limit]
            retrieval = {
                "strategy": "recent_memory_fallback",
                "error_category": "retrieval_failed",
            }
            status = "fallback"
            error = "memory_retrieval_failed"

        public_metadata = {
            key: retrieval.get(key)
            for key in (
                "strategy",
                "provider",
                "model",
                "candidate_count",
                "dense_candidate_count",
                "sparse_candidate_count",
                "error_category",
            )
            if retrieval.get(key) is not None
        }
        return AgentResult(
            agent=self.name,
            status=status,
            summary=f"Retrieved {len(memories)} relevant memories.",
            artifact={
                "memories": memories,
                "memory_retrieval": retrieval,
            },
            metadata=public_metadata,
            error=error,
        )

    @staticmethod
    def _default_query(context: AgentRunContext) -> str:
        goals = context.inputs.get("goals", [])
        goal_text = " ".join(
            f"{goal.get('title', '')} {goal.get('description', '')}"
            for goal in goals
            if isinstance(goal, dict)
        )
        return f"{context.user_name} {context.workflow} {goal_text}".strip()


class PlannerAgent:
    name = "planner"

    def __init__(self, service: NexusService):
        self.service = service

    def run(self, context: AgentRunContext) -> AgentResult:
        now = context.inputs.get("now")
        tool_context = context.artifacts.get(
            "tool",
            context.inputs.get("mcp_context", {"results": [], "errors": []}),
        )
        if context.workflow == "briefing":
            response = self.service.daily_briefing(
                user_name=context.user_name,
                weather=context.inputs.get("weather"),
                now=now,
                use_llm=False,
                mcp_context=tool_context,
                external_context=context.inputs.get("external_context"),
                memory_context=context.artifacts.get("memory"),
            )
            response["mcp_context"] = tool_context
            field = "briefing"
        else:
            response = self.service.daily_plan(
                user_name=context.user_name,
                now=now,
                coach_mode=context.coach_mode,
                use_llm=False,
                mcp_context=tool_context,
                memory_context=context.artifacts.get("memory"),
            )
            field = "plan"
        return AgentResult(
            agent=self.name,
            status="completed",
            summary=f"Prepared {context.workflow} priorities.",
            artifact={"response": response, "response_field": field},
            metadata={
                "task_count": len(response.get("tasks", [])),
                "tool_result_count": len(tool_context.get("results", [])),
                "tool_error_count": len(tool_context.get("errors", [])),
            },
        )


class ReflectionAgent:
    name = "reflection"

    def __init__(self, service: NexusService):
        self.service = service

    def run(self, context: AgentRunContext) -> AgentResult:
        response = self.service.daily_review(
            user_name=context.user_name,
            now=context.inputs.get("now"),
            use_llm=False,
            coach_mode=context.coach_mode,
            memory_context=context.artifacts.get("memory"),
        )
        return AgentResult(
            agent=self.name,
            status="completed",
            summary="Reviewed outcomes, blockers, and carry-forward work.",
            artifact={"response": response, "response_field": "review"},
            metadata={
                "completed_task_count": len(response.get("completed_tasks", [])),
                "blocked_task_count": len(response.get("blocked_tasks", [])),
                "unresolved_task_count": len(response.get("unresolved_tasks", [])),
            },
        )


class CoachAgent:
    name = "coach"

    def __init__(self, service: NexusService):
        self.service = service

    def run(self, context: AgentRunContext) -> AgentResult:
        source_name = "reflection" if context.workflow == "review" else "planner"
        source = context.artifacts[source_name]
        response = dict(source["response"])
        response_field = source.get(
            "response_field",
            {"plan": "plan", "review": "review", "briefing": "briefing"}[
                context.workflow
            ],
        )
        profile = coach_profile(context.coach_mode)
        fallback = response.get(response_field, "")
        response[response_field] = (
            f"{fallback}\n\n[{profile.mode} coach] {profile.closing}".strip()
        )
        llm_info = dict(response.get("llm") or {})
        llm_info.update({"requested": context.use_llm, "used": False, "error": None})

        status = "completed"
        error: str | None = None
        if context.use_llm:
            if self.service.llm is None:
                status = "fallback"
                error = "LLM client is not configured."
                llm_info["error"] = error
            else:
                try:
                    context.budget.consume_llm()
                    response[response_field] = self._generate_llm(
                        context,
                        (
                            "You are Nexus Coach. Respond in Chinese. "
                            f"Use {profile.label} behavior: {profile.instruction}"
                        ),
                        self._user_prompt(context, response, response_field),
                    )
                    llm_info["used"] = True
                except (AgentBudgetExceeded, LLMError) as exc:
                    status = "fallback"
                    error = str(exc)
                    llm_info["error"] = error
        response["llm"] = llm_info
        return AgentResult(
            agent=self.name,
            status=status,
            summary=f"Applied {profile.mode} coaching mode.",
            artifact={"response": response},
            metadata={"coach_mode": profile.mode, "llm_used": llm_info["used"]},
            error=error,
        )

    def _generate_llm(
        self,
        context: AgentRunContext,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        if isinstance(self.service.llm, OpenAICompatibleLLM):
            return self.service.llm.generate(
                system_prompt,
                user_prompt,
                timeout_seconds=context.budget.remaining_seconds(),
            )
        return self.service.llm.generate(system_prompt, user_prompt)

    @staticmethod
    def _user_prompt(
        context: AgentRunContext,
        response: dict[str, Any],
        response_field: str,
    ) -> str:
        public_context = {
            key: value
            for key, value in response.items()
            if key not in {response_field, "llm", "prompt"}
        }
        return (
            f"Create the final {context.workflow} response for {context.user_name}.\n"
            "Use only this structured Nexus context:\n"
            f"{json.dumps(public_context, ensure_ascii=False, default=str)}"
        )
