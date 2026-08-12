from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from nexus.conversation import ConversationService, IntentRegistry
from nexus.service import NexusService
from nexus.store import JsonStore


NOW = datetime(2026, 8, 8, 9, 0, tzinfo=UTC)


def service(tmp_path: Path, llm: object | None = None) -> ConversationService:
    nexus = NexusService(JsonStore(tmp_path / "state.json"), llm=llm)
    return ConversationService(nexus, timezone="UTC", llm=llm)


def test_local_registry_handles_chinese_and_english_reads() -> None:
    registry = IntentRegistry()
    assert registry.parse_local("show my goals").name == "list_goals"
    assert registry.parse_local("查看我的习惯").name == "list_habits"
    assert registry.parse_local("列出项目").name == "list_projects"
    assert registry.parse_local("something ambiguous") is None
    assert registry.parse_local("list research").name == "list_research"
    assert registry.parse_local("查看研究项目").name == "list_research"


def test_mutation_previews_before_approval_and_then_executes(tmp_path: Path) -> None:
    conversation = service(tmp_path)
    preview = conversation.handle("remember Nexus is my AIOS project", now=NOW)
    assert preview["requires_approval"] is True
    assert preview["result"] is None
    assert preview["preview"]["arguments"]["text"] == "Nexus is my AIOS project"

    accepted = conversation.handle(
        "remember Nexus is my AIOS project", approved=True, now=NOW
    )
    assert accepted["result"]["memory"]["text"] == "Nexus is my AIOS project"


def test_explicit_habit_check_in_is_low_risk(tmp_path: Path) -> None:
    nexus = NexusService(JsonStore(tmp_path / "state.json"))
    habit = nexus.add_habit("Read", "", "daily", (), 1, None, timezone="UTC", now=NOW)
    conversation = ConversationService(nexus, timezone="UTC")
    result = conversation.handle(f"check in habit {habit['id']}", now=NOW)
    assert result["requires_approval"] is False
    assert result["result"]["summary"]["today_complete"] is True


def test_llm_parser_accepts_strict_known_intent_and_rejects_unknown_schema(
    tmp_path: Path,
) -> None:
    class FakeLLM:
        response = json.dumps(
            {"intent": "list_projects", "arguments": {}, "confidence": 0.91}
        )

        def generate(self, _system: str, _user: str) -> str:
            return self.response

    llm = FakeLLM()
    conversation = service(tmp_path, llm=llm)
    parsed = conversation.handle("what am I building", use_llm=True, now=NOW)
    assert parsed["intent"] == "list_projects"
    assert parsed["source"] == "llm"

    llm.response = json.dumps(
        {"intent": "run_shell", "arguments": {"command": "whoami"}, "confidence": 1}
    )
    rejected = conversation.handle("do something", use_llm=True, now=NOW)
    assert rejected["intent"] == "unknown"
    assert rejected["degradations"] == ["llm_intent_rejected"]


def test_project_progress_requires_approval(tmp_path: Path) -> None:
    nexus = NexusService(JsonStore(tmp_path / "state.json"))
    project = nexus.add_project("Nexus", "", 1, None, (), (), now=NOW)
    conversation = ConversationService(nexus)
    text = f"project {project['id']} progress 40"
    assert (
        conversation.handle(text, now=NOW)["preview"]["intent"]
        == "update_project_progress"
    )
    result = conversation.handle(text, approved=True, now=NOW)
    assert result["result"]["summary"]["progress_percent"] == 40


def test_conversation_lists_and_shows_research(tmp_path: Path) -> None:
    nexus = NexusService(JsonStore(tmp_path / "state.json"))
    project = nexus.create_research("RAG", "Evaluate retrieval.", "", now=NOW)
    conversation = ConversationService(nexus)

    listed = conversation.handle("list research", now=NOW)
    shown = conversation.handle(f"show research {project['id']}", now=NOW)

    assert listed["result"]["research"][0]["id"] == project["id"]
    assert shown["result"]["research"]["title"] == "RAG"
