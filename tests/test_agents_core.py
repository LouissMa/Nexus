from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.agents.models import (
    AgentBudget,
    AgentBudgetExceeded,
    AgentResult,
    AgentRunTrace,
    AgentStepTrace,
)
from nexus.agents.trace import AgentTraceStore


def test_agent_budget_enforces_each_limit() -> None:
    budget = AgentBudget(
        max_steps=2,
        max_llm_calls=1,
        max_tool_calls=1,
        max_seconds=60,
    )

    budget.consume_step()
    budget.consume_step()
    budget.consume_llm()
    budget.consume_tool()

    with pytest.raises(AgentBudgetExceeded, match="step"):
        budget.consume_step()
    with pytest.raises(AgentBudgetExceeded, match="LLM"):
        budget.consume_llm()
    with pytest.raises(AgentBudgetExceeded, match="tool"):
        budget.consume_tool()

    assert budget.to_dict()["used"] == {
        "steps": 2,
        "llm_calls": 1,
        "tool_calls": 1,
    }


def test_agent_budget_rejects_work_after_deadline() -> None:
    moments = iter([10.0, 11.1])
    budget = AgentBudget(max_seconds=1, clock=lambda: next(moments))

    with pytest.raises(AgentBudgetExceeded, match="time"):
        budget.consume_step()


def test_agent_result_serializes_public_fields_without_internal_artifact() -> None:
    result = AgentResult(
        agent="memory",
        status="completed",
        summary="Retrieved 2 memories.",
        artifact={"memories": [{"text": "private life detail"}]},
        metadata={"strategy": "hybrid", "candidate_count": 4},
    )

    assert result.to_public_dict() == {
        "agent": "memory",
        "status": "completed",
        "summary": "Retrieved 2 memories.",
        "metadata": {"strategy": "hybrid", "candidate_count": 4},
        "error": None,
    }


def test_trace_store_persists_reads_and_finds_runs(tmp_path: Path) -> None:
    path = tmp_path / "agent_runs.jsonl"
    store = AgentTraceStore(path)
    trace = make_trace("run-1")

    store.append(trace)

    assert store.recent() == [trace.to_dict()]
    assert store.find("run-1") == trace.to_dict()
    assert store.find("missing") is None


def test_trace_store_ignores_corrupt_lines_and_missing_files(tmp_path: Path) -> None:
    path = tmp_path / "agent_runs.jsonl"
    store = AgentTraceStore(path)
    assert store.recent() == []

    path.write_text('not json\n{"run_id": "valid"}\n', encoding="utf-8")
    assert store.recent() == [{"run_id": "valid"}]


def test_trace_store_redacts_secrets_prompts_and_argument_values(
    tmp_path: Path,
) -> None:
    store = AgentTraceStore(tmp_path / "agent_runs.jsonl")
    trace = make_trace(
        "run-secret",
        metadata={
            "server": "research",
            "tool": "search",
            "arguments": {
                "query": "private research topic",
                "api_key": "sk-sensitive",
            },
            "prompt": "full private prompt",
            "query": "plain private goal details",
            "error": "private provider response",
            "nested": {
                "authorization": "Bearer hidden",
                "url": "https://secret.example/mcp?token=hidden",
            },
        },
    )

    store.append(trace)
    encoded = json.dumps(store.recent(), ensure_ascii=False)

    assert "private research topic" not in encoded
    assert "sk-sensitive" not in encoded
    assert "full private prompt" not in encoded
    assert "plain private goal details" not in encoded
    assert "private provider response" not in encoded
    assert "Bearer hidden" not in encoded
    assert "secret.example" not in encoded
    assert '"argument_keys": ["api_key", "query"]' in encoded


def test_trace_write_is_best_effort_for_unserializable_metadata(tmp_path: Path) -> None:
    store = AgentTraceStore(tmp_path / "agent_runs.jsonl")
    trace = make_trace("run-unserializable", metadata={"value": object()})

    store.append(trace)

    assert store.recent() == []


def make_trace(
    run_id: str,
    metadata: dict[str, object] | None = None,
) -> AgentRunTrace:
    now = datetime(2026, 7, 26, 8, 0, tzinfo=UTC)
    return AgentRunTrace(
        run_id=run_id,
        workflow="plan",
        user_name="User",
        started_at=now.isoformat(),
        completed_at=now.isoformat(),
        status="completed",
        duration_ms=12,
        steps=[
            AgentStepTrace(
                agent="tool",
                status="completed",
                duration_ms=5,
                summary="Called one approved tool.",
                metadata=metadata or {},
            )
        ],
        budget={
            "limits": {
                "steps": 8,
                "llm_calls": 3,
                "tool_calls": 3,
                "seconds": 60,
            },
            "used": {"steps": 1, "llm_calls": 0, "tool_calls": 1},
        },
    )
