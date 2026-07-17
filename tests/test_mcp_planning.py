from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nexus.service import NexusService
from nexus.store import JsonStore


class FakeLLM:
    def __init__(self) -> None:
        self.user_prompt = ""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.user_prompt = user_prompt
        return "MCP-aware plan"


def test_daily_plan_includes_mcp_context_in_output_template_and_prompt(
    tmp_path: Path,
) -> None:
    llm = FakeLLM()
    service = NexusService(JsonStore(tmp_path / "state.json"), llm=llm)
    service.add_goal("Research MCP", "Read protocol papers", 1)
    context = {
        "results": [
            {
                "server": "research",
                "tool": "search",
                "text": ["Two relevant papers found"],
                "structured_data": {"count": 2},
                "content_metadata": [],
                "is_error": False,
                "attempt_count": 1,
                "executed_at": "2030-01-03T00:00:00+00:00",
            }
        ],
        "errors": [],
    }

    local = service.daily_plan(
        user_name="Louis",
        now=datetime(2030, 1, 3, tzinfo=UTC),
        mcp_context=context,
    )
    assert local["mcp_context"] == context
    assert "Two relevant papers found" in local["plan"]

    generated = service.daily_plan(
        user_name="Louis",
        now=datetime(2030, 1, 3, tzinfo=UTC),
        use_llm=True,
        include_prompt=True,
        mcp_context=context,
    )
    assert generated["plan"] == "MCP-aware plan"
    assert "Two relevant papers found" in generated["prompt"]["user"]
    assert "Two relevant papers found" in llm.user_prompt


def test_daily_plan_preserves_mcp_errors_without_failing(tmp_path: Path) -> None:
    service = NexusService(JsonStore(tmp_path / "state.json"))
    context = {
        "results": [],
        "errors": [
            {"server": "offline", "tool": "search", "error": "connection failed"}
        ],
    }
    plan = service.daily_plan(
        now=datetime(2030, 1, 3, tzinfo=UTC),
        mcp_context=context,
    )
    assert plan["mcp_context"] == context
    assert "offline/search: connection failed" in plan["plan"]
