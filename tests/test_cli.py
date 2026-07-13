from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from nexus.config import load_llm_settings
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


def test_memory_goal_review_and_rag_briefing_flow(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["NEXUS_HOME"] = str(tmp_path / "nexus-home")
    env.pop("NEXUS_LLM_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)

    memory = run_cli("memory", "add", "User wants to practice English daily", "--tags", "learning", env=env)
    assert memory["status"] == "ok"
    run_cli("memory", "add", "User is building a personal AI operating system called Nexus", "--tags", "project", env=env)

    state = json.loads((tmp_path / "nexus-home" / "state.json").read_text(encoding="utf-8"))
    assert "embedding" in state["memories"][0]

    goal = run_cli("goal", "add", "Practice English", "--description", "15 minutes speaking", "--cadence-days", "1", env=env)
    goal_id = goal["goal"]["id"]

    search = run_cli("memory", "search", "English", env=env)
    assert len(search["results"]) == 1
    assert "embedding" not in search["results"][0]

    retrieved = run_cli("memory", "retrieve", "English speaking practice", "--limit", "1", env=env)
    assert retrieved["results"][0]["text"] == "User wants to practice English daily"
    assert retrieved["results"][0]["retrieval_score"] > 0
    assert "embedding" not in retrieved["results"][0]

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
    assert briefing["today"]["date"] == "1\u67083\u65e5"
    assert briefing["important_goals"][0]["id"] == goal_id
    assert briefing["relevant_memories"][0]["text"] == "User wants to practice English daily"
    assert briefing["memory_retrieval"]["strategy"] == "local_sparse_embedding"
    assert briefing["llm"] == {"requested": False, "used": False, "error": None}
    assert "Practice English" in briefing["briefing"]
    assert "Louis" in briefing["briefing"]

    check_in = run_cli("goal", "check-in", goal_id, "Completed today's English session", env=env)
    assert check_in["status"] == "ok"

    daily_review = run_cli("review", "day", "--name", "Louis", env=env)
    assert daily_review["user_name"] == "Louis"
    assert daily_review["completed_goals"][0]["id"] == goal_id
    assert daily_review["today_check_ins"][0]["note"] == "Completed today's English session"
    assert daily_review["memory_retrieval"]["strategy"] == "local_sparse_embedding"
    assert "Practice English" in daily_review["review"]
    assert daily_review["tomorrow_priorities"]

    llm_fallback = run_cli(
        "review",
        "day",
        "--llm",
        "--show-prompt",
        env=env,
    )
    assert llm_fallback["llm"]["requested"] is True
    assert llm_fallback["llm"]["used"] is False
    assert "not configured" in llm_fallback["llm"]["error"]
    assert "evening daily review" in llm_fallback["prompt"]["user"]
    assert "Memory retrieval" in llm_fallback["prompt"]["user"]


def test_llm_config_set_and_show_masks_api_key(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["NEXUS_HOME"] = str(tmp_path / "nexus-home")
    env.pop("NEXUS_LLM_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)

    saved = run_cli(
        "config",
        "llm",
        "set",
        "--provider",
        "deepseek",
        "--api-key",
        "sk-test-secret-value",
        "--simple-model",
        "v4flash",
        "--complex-model",
        "v4pro",
        "--default-tier",
        "simple",
        env=env,
    )

    assert saved["status"] == "ok"
    assert saved["llm"]["provider"] == "deepseek"
    assert saved["llm"]["api_key"] == "sk-t...alue"
    assert "sk-test-secret-value" not in json.dumps(saved)

    config_path = tmp_path / "nexus-home" / "config.local.json"
    assert config_path.exists()
    settings = load_llm_settings(env={}, path=config_path)
    assert settings.provider == "deepseek"
    assert settings.api_key == "sk-test-secret-value"
    assert settings.model_for_tier("simple") == "v4flash"
    assert settings.model_for_tier("complex") == "v4pro"

    shown = run_cli("config", "llm", "show", env=env)
    assert shown["llm"]["api_key"] == "sk-t...alue"
    assert "sk-test-secret-value" not in json.dumps(shown)


class FakeLLM:
    def __init__(self) -> None:
        self.system_prompt = ""
        self.user_prompt = ""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return "LLM generated output"


def test_daily_briefing_uses_injected_llm_and_rag_context(tmp_path: Path) -> None:
    store = JsonStore(tmp_path / "state.json")
    fake_llm = FakeLLM()
    service = NexusService(store, llm=fake_llm)

    service.add_memory("Louis is building Nexus as a personal AI OS", ["project"])
    service.add_memory("Louis wants to improve IELTS listening", ["study"])
    service.add_goal("Build LLM briefing", "Use memories and goals in the prompt", 1)

    briefing = service.daily_briefing(
        user_name="Louis",
        weather="\u5929\u6c14\u6674\uff0c\u6700\u9ad8 25 C",
        now=None,
        use_llm=True,
        include_prompt=True,
    )

    assert briefing["briefing"] == "LLM generated output"
    assert briefing["llm"]["used"] is True
    assert briefing["memory_retrieval"]["strategy"] == "local_sparse_embedding"
    assert "proactive personal AI life assistant" in fake_llm.system_prompt
    assert "Louis is building Nexus" in fake_llm.user_prompt
    assert "Memory retrieval" in fake_llm.user_prompt
    assert "Build LLM briefing" in fake_llm.user_prompt
    assert briefing["prompt"]["user"] == fake_llm.user_prompt


def test_daily_review_uses_injected_llm_and_reflection_context(tmp_path: Path) -> None:
    store = JsonStore(tmp_path / "state.json")
    fake_llm = FakeLLM()
    service = NexusService(store, llm=fake_llm)

    service.add_memory("Louis is building Nexus as a personal AI OS", ["project"])
    goal = service.add_goal("Build Daily Review", "Create evening reflection loop", 1)
    service.check_in_goal(goal.id, "Implemented the review command")

    review = service.daily_review(
        user_name="Louis",
        use_llm=True,
        include_prompt=True,
    )

    assert review["review"] == "LLM generated output"
    assert review["llm"]["used"] is True
    assert review["completed_goals"][0]["id"] == goal.id
    assert "evening daily review" in fake_llm.user_prompt
    assert "Build Daily Review" in fake_llm.user_prompt
    assert "Implemented the review command" in fake_llm.user_prompt
    assert review["prompt"]["user"] == fake_llm.user_prompt


def test_daily_planning_tasks_blockers_and_coach_modes(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["NEXUS_HOME"] = str(tmp_path / "nexus-home")
    env.pop("NEXUS_LLM_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)

    run_cli("goal", "add", "Prepare IELTS", "--description", "Complete one listening set", env=env)
    run_cli("goal", "add", "Build Nexus", "--description", "Implement the planning module", env=env)

    plan = run_cli(
        "plan", "day", "--name", "Louis", "--coach-mode", "academic",
        "--now", "2030-01-03T08:00:00+00:00", "--show-prompt", env=env,
    )
    assert plan["plan_date"] == "2030-01-03"
    assert plan["coach_mode"] == "academic"
    assert len(plan["tasks"]) == 2
    assert plan["tasks"][0]["goal_id"]
    assert plan["tasks"][0]["status"] == "pending"
    assert "academic study coach" in plan["prompt"]["system"]

    repeated = run_cli("plan", "day", "--now", "2030-01-03T09:00:00+00:00", env=env)
    assert [task["id"] for task in repeated["tasks"]] == [task["id"] for task in plan["tasks"]]

    task_id = plan["tasks"][0]["id"]
    updated = run_cli(
        "task", "update", task_id,
        "--blocker", "Need a practice audio source",
        "--unresolved", "Choose tomorrow's audio set",
        "--note", "Reviewed the test format",
        env=env,
    )
    assert updated["task"]["status"] == "blocked"
    assert updated["task"]["blocker"] == "Need a practice audio source"
    assert updated["task"]["unresolved"] == ["Choose tomorrow's audio set"]

    completed_task_id = plan["tasks"][1]["id"]
    completed = run_cli("task", "update", completed_task_id, "--status", "completed", env=env)
    assert completed["task"]["status"] == "completed"
    review = run_cli(
        "review", "day", "--name", "Louis", "--coach-mode", "strict",
        "--now", "2030-01-03T20:00:00+00:00", "--show-prompt", env=env,
    )
    assert review["coach_mode"] == "strict"
    assert review["completed_tasks"][0]["id"] == completed_task_id
    assert review["blocked_tasks"][0]["id"] == task_id
    assert review["unresolved_tasks"][0]["item"] == "Choose tomorrow's audio set"
    assert "Need a practice audio source" in review["review"]
    assert "strict execution coach" in review["prompt"]["system"]
    assert "Structured unresolved items" in review["prompt"]["user"]
    assert review["tomorrow_priorities"][0].startswith("Resolve blocker")

    listed = run_cli("task", "list", "--date", "2030-01-03", env=env)
    assert len(listed["tasks"]) == 2
