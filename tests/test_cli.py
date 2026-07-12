from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from nexus.service import NexusService
from nexus.store import JsonStore


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, env: dict[str, str]) -> dict:
    command = [sys.executable, "-m", "nexus.cli", *args]
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_memory_goal_and_review_flow(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["NEXUS_HOME"] = str(tmp_path / "nexus-home")
    env.pop("NEXUS_LLM_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)

    memory = run_cli("memory", "add", "User wants to practice English daily", "--tags", "learning", env=env)
    assert memory["status"] == "ok"

    goal = run_cli("goal", "add", "Practice English", "--description", "15 minutes speaking", "--cadence-days", "1", env=env)
    goal_id = goal["goal"]["id"]

    search = run_cli("memory", "search", "English", env=env)
    assert len(search["results"]) == 1

    review = run_cli("review", "--now", "2030-01-03T00:00:00+00:00", env=env)
    assert any(goal_id in reminder for reminder in review["reminders"])

    briefing = run_cli(
        "briefing",
        "--name",
        "Louis",
        "--weather",
        "weather is sunny, high 25 C",
        "--now",
        "2030-01-03T08:00:00+00:00",
        env=env,
    )
    assert briefing["user_name"] == "Louis"
    assert briefing["today"]["date"] == "1月3日"
    assert briefing["important_goals"][0]["id"] == goal_id
    assert briefing["relevant_memories"][0]["text"] == "User wants to practice English daily"
    assert briefing["llm"] == {"requested": False, "used": False, "error": None}
    assert "Practice English" in briefing["briefing"]
    assert "Louis" in briefing["briefing"]

    llm_fallback = run_cli(
        "briefing",
        "--llm",
        "--show-prompt",
        "--now",
        "2030-01-03T08:00:00+00:00",
        env=env,
    )
    assert llm_fallback["llm"]["requested"] is True
    assert llm_fallback["llm"]["used"] is False
    assert "not configured" in llm_fallback["llm"]["error"]
    assert "prompt" in llm_fallback

    check_in = run_cli("goal", "check-in", goal_id, "Completed today's session", env=env)
    assert check_in["status"] == "ok"


class FakeLLM:
    def __init__(self) -> None:
        self.system_prompt = ""
        self.user_prompt = ""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return "LLM generated briefing"


def test_daily_briefing_uses_injected_llm(tmp_path: Path) -> None:
    store = JsonStore(tmp_path / "state.json")
    fake_llm = FakeLLM()
    service = NexusService(store, llm=fake_llm)

    service.add_memory("Louis is building Nexus as a personal AI OS", ["project"])
    service.add_goal("Build LLM briefing", "Use memories and goals in the prompt", 1)

    briefing = service.daily_briefing(
        user_name="Louis",
        weather="天气晴，最高 25 C",
        now=None,
        use_llm=True,
        include_prompt=True,
    )

    assert briefing["briefing"] == "LLM generated briefing"
    assert briefing["llm"]["used"] is True
    assert "proactive personal AI life assistant" in fake_llm.system_prompt
    assert "Louis is building Nexus" in fake_llm.user_prompt
    assert "Build LLM briefing" in fake_llm.user_prompt
    assert briefing["prompt"]["user"] == fake_llm.user_prompt
