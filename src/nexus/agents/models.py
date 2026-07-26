from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Callable


class AgentBudgetExceeded(RuntimeError):
    """Raised before an agent run exceeds one of its configured limits."""


@dataclass
class AgentBudget:
    max_steps: int = 8
    max_llm_calls: int = 3
    max_tool_calls: int = 3
    max_seconds: float = 60
    clock: Callable[[], float] = field(default=monotonic, repr=False)
    used_steps: int = 0
    used_llm_calls: int = 0
    used_tool_calls: int = 0
    _started: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            min(
                self.max_steps,
                self.max_llm_calls,
                self.max_tool_calls,
                self.max_seconds,
            )
            < 0
        ):
            raise ValueError("Agent budget limits cannot be negative.")
        self._started = self.clock()

    def consume_step(self) -> None:
        self.check_time()
        if self.used_steps >= self.max_steps:
            raise AgentBudgetExceeded("Agent step budget exhausted.")
        self.used_steps += 1

    def consume_llm(self) -> None:
        self.check_time()
        if self.used_llm_calls >= self.max_llm_calls:
            raise AgentBudgetExceeded("Agent LLM call budget exhausted.")
        self.used_llm_calls += 1

    def consume_tool(self) -> None:
        self.check_time()
        if self.used_tool_calls >= self.max_tool_calls:
            raise AgentBudgetExceeded("Agent tool call budget exhausted.")
        self.used_tool_calls += 1

    def check_time(self) -> None:
        if self.clock() - self._started > self.max_seconds:
            raise AgentBudgetExceeded("Agent time budget exhausted.")

    def remaining_seconds(self) -> float:
        return max(0.0, self.max_seconds - (self.clock() - self._started))

    def to_dict(self) -> dict[str, Any]:
        return {
            "limits": {
                "steps": self.max_steps,
                "llm_calls": self.max_llm_calls,
                "tool_calls": self.max_tool_calls,
                "seconds": self.max_seconds,
            },
            "used": {
                "steps": self.used_steps,
                "llm_calls": self.used_llm_calls,
                "tool_calls": self.used_tool_calls,
            },
        }


@dataclass
class AgentRunContext:
    run_id: str
    workflow: str
    user_name: str
    coach_mode: str
    started_at: str
    budget: AgentBudget
    inputs: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    use_llm: bool = False


@dataclass
class AgentResult:
    agent: str
    status: str
    summary: str
    artifact: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "status": self.status,
            "summary": self.summary,
            "metadata": self.metadata,
            "error": self.error,
        }


@dataclass
class AgentStepTrace:
    agent: str
    status: str
    duration_ms: int
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def remaining_seconds(self) -> float:
        return max(0.0, self.max_seconds - (self.clock() - self._started))

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "summary": self.summary,
            "metadata": self.metadata,
            "error": self.error,
        }


@dataclass
class AgentRunTrace:
    run_id: str
    workflow: str
    user_name: str
    started_at: str
    completed_at: str
    status: str
    duration_ms: int
    steps: list[AgentStepTrace]
    budget: dict[str, Any]

    def remaining_seconds(self) -> float:
        return max(0.0, self.max_seconds - (self.clock() - self._started))

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workflow": self.workflow,
            "user_name": self.user_name,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "steps": [step.to_dict() for step in self.steps],
            "budget": self.budget,
        }
