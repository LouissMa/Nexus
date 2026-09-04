from __future__ import annotations

import argparse
import json
import threading
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .agents.orchestrator import AgentOrchestrator
from .agents.trace import AgentTraceStore
from .automation import (
    AutomationConfigurationError,
    AutomationError,
    AutomationExecutionError,
    AutomationManager,
    AutomationPermissionError,
    load_automation_settings,
    masked_automation_settings,
    remove_automation,
    upsert_automation,
)
from .config import (
    disable_voice_settings,
    load_embedding_settings,
    load_llm_settings,
    load_local_config,
    load_nexus_mcp_server_policies,
    load_runtime_settings,
    load_tool_settings,
    load_voice_settings,
    masked_tool_settings,
    patch_profile_settings,
    patch_runtime_settings,
    nexus_home,
    update_embedding_settings,
    update_llm_settings,
    update_tool_settings,
    update_voice_settings,
)
from .conversation import ConversationService
from .dashboard import DashboardActions, DashboardServer, DashboardSnapshot
from .integrations.core import ToolError
from .integrations.manager import build_tool_manager
from .llm import LLMConfig, OpenAICompatibleLLM
from .mcp.config import (
    disable_mcp_server,
    load_mcp_settings,
    masked_mcp_settings,
    remove_mcp_server,
    set_mcp_planning_tool,
    set_mcp_tool_policy,
    upsert_mcp_server,
)
from .mcp.manager import build_mcp_manager
from .mcp.models import MCPError
from .mcp_server import NEXUS_MCP_TOOL_NAMES, NexusMCPTools, run_stdio_server
from .memory_lifecycle import MemoryLifecycleError, PRIVACY_SCOPES
from .notifications import NotificationCenter
from .planning import COACH_MODES, TASK_STATUSES
from .rag import build_memory_retriever
from .runtime_config import (
    RUNTIME_JOB_NAMES,
    ProfileSettings,
    RuntimeSettings,
    profile_settings_from_mapping,
)
from .scheduler import ProactiveScheduler
from .service import NexusService
from .store import JsonStore
from .voice import (
    VoiceConfigurationError,
    VoiceError,
    VoiceService,
    validate_audio_file,
)
from .voice_providers import (
    build_voice_providers,
    voice_provider_availability,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nexus",
        description="Nexus personal AI: memory, planning, reflection, hybrid RAG, and permissioned tools.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_parser = subparsers.add_parser(
        "ask", help="Use the unified local-first conversation entry point."
    )
    ask_parser.add_argument("text")
    ask_parser.add_argument("--approve", action="store_true")
    ask_parser.add_argument("--llm", action="store_true")
    ask_parser.add_argument("--model-tier", choices=["simple", "complex"])
    ask_parser.add_argument("--show-intent", action="store_true")
    ask_parser.add_argument("--now")
    memory_parser = subparsers.add_parser("memory", help="Manage long-term memories.")
    memory_subparsers = memory_parser.add_subparsers(
        dest="memory_command", required=True
    )

    memory_add = memory_subparsers.add_parser("add", help="Store a memory.")
    memory_add.add_argument("text", help="Memory text to store.")
    memory_add.add_argument("--tags", nargs="*", default=[], help="Optional tags.")
    memory_add.add_argument("--importance", type=float)
    memory_add.add_argument("--privacy", choices=PRIVACY_SCOPES, default="private")
    memory_add.add_argument("--expires-at", help="Optional ISO expiry timestamp.")
    memory_add.add_argument("--pin", action="store_true")

    memory_list = memory_subparsers.add_parser("list", help="List memories.")
    memory_list.add_argument("--include-archived", action="store_true")
    memory_list.add_argument("--include-forgotten", action="store_true")

    memory_show = memory_subparsers.add_parser("show", help="Show one memory.")
    memory_show.add_argument("memory_id")

    memory_search = memory_subparsers.add_parser(
        "search", help="Search memories by keyword."
    )
    memory_search.add_argument("query", help="Keyword query.")

    memory_retrieve = memory_subparsers.add_parser(
        "retrieve", help="Retrieve relevant memories with local RAG."
    )
    memory_retrieve.add_argument("query", help="Semantic retrieval query.")
    memory_retrieve.add_argument(
        "--limit", type=int, default=5, help="Maximum number of memories to return."
    )
    memory_retrieve.add_argument("--privacy", choices=PRIVACY_SCOPES, default="private")
    memory_retrieve.add_argument("--include-archived", action="store_true")
    memory_retrieve.add_argument("--task-context")
    memory_retrieve.add_argument(
        "--now", help="Optional ISO timestamp for deterministic retrieval."
    )

    memory_update = memory_subparsers.add_parser(
        "update", help="Update memory controls."
    )
    memory_update.add_argument("memory_id")
    memory_update.add_argument("--importance", type=float)
    memory_update.add_argument("--privacy", choices=PRIVACY_SCOPES)
    memory_update.add_argument("--expires-at", help="ISO timestamp or 'none' to clear.")
    pin_group = memory_update.add_mutually_exclusive_group()
    pin_group.add_argument("--pin", action="store_true")
    pin_group.add_argument("--unpin", action="store_true")

    memory_relate = memory_subparsers.add_parser("relate", help="Link memory history.")
    memory_relate.add_argument("memory_id")
    relation_group = memory_relate.add_mutually_exclusive_group(required=True)
    relation_group.add_argument("--supersedes", metavar="MEMORY_ID")
    relation_group.add_argument("--conflicts-with", metavar="MEMORY_ID")

    for command_name in ("archive", "restore", "forget"):
        lifecycle_parser = memory_subparsers.add_parser(command_name)
        lifecycle_parser.add_argument("memory_id")

    memory_purge = memory_subparsers.add_parser(
        "purge", help="Permanently remove a forgotten memory."
    )
    memory_purge.add_argument("memory_id")
    memory_purge.add_argument("--confirm", action="store_true")

    memory_compress = memory_subparsers.add_parser(
        "compress", help="Summarize and archive old low-importance memories."
    )
    memory_compress.add_argument("--older-than-days", type=int, default=90)
    memory_compress.add_argument("--max-importance", type=float, default=0.4)
    memory_compress.add_argument("--dry-run", action="store_true")
    memory_compress.add_argument("--now", help="Optional ISO timestamp.")

    memory_maintain = memory_subparsers.add_parser(
        "maintain", help="Apply expiry retention rules."
    )
    memory_maintain.add_argument("--dry-run", action="store_true")
    memory_maintain.add_argument("--now", help="Optional ISO timestamp.")

    memory_subparsers.add_parser("reindex", help="Rebuild the semantic memory index.")
    memory_subparsers.add_parser(
        "index-status", help="Show semantic memory index status."
    )
    goal_parser = subparsers.add_parser("goal", help="Manage tracked goals.")
    goal_subparsers = goal_parser.add_subparsers(dest="goal_command", required=True)

    goal_add = goal_subparsers.add_parser("add", help="Create a goal.")
    goal_add.add_argument("title", help="Goal title.")
    goal_add.add_argument("--description", default="", help="Goal description.")
    goal_add.add_argument(
        "--cadence-days", type=int, default=3, help="Check-in cadence in days."
    )

    goal_subparsers.add_parser("list", help="List goals.")

    goal_check_in = goal_subparsers.add_parser(
        "check-in", help="Record progress on a goal."
    )
    goal_check_in.add_argument("goal_id", help="Goal identifier.")
    goal_check_in.add_argument("note", help="Short progress note.")

    habit_parser = subparsers.add_parser("habit", help="Manage habits.")
    habit_subparsers = habit_parser.add_subparsers(dest="habit_command", required=True)
    habit_add = habit_subparsers.add_parser("add", help="Create a habit.")
    habit_add.add_argument("name")
    habit_add.add_argument("--description", default="")
    habit_add.add_argument("--cadence", choices=["daily", "weekdays"], default="daily")
    habit_add.add_argument("--weekday", action="append", type=int, default=[])
    habit_add.add_argument("--target-count", type=int, default=1)
    habit_add.add_argument("--goal-id")
    habit_add.add_argument("--now")
    habit_list = habit_subparsers.add_parser("list", help="List habits.")
    habit_list.add_argument("--include-archived", action="store_true")
    habit_list.add_argument("--now")
    habit_check = habit_subparsers.add_parser(
        "check-in", help="Record a habit check-in."
    )
    habit_check.add_argument("habit_id")
    habit_check.add_argument("--date")
    habit_check.add_argument("--count", type=int, default=1)
    habit_check.add_argument("--note", default="")
    habit_check.add_argument("--now")
    habit_archive = habit_subparsers.add_parser("archive", help="Archive a habit.")
    habit_archive.add_argument("habit_id")
    habit_archive.add_argument("--now")

    project_parser = subparsers.add_parser("project", help="Manage projects.")
    project_subparsers = project_parser.add_subparsers(
        dest="project_command", required=True
    )
    project_add = project_subparsers.add_parser("add", help="Create a project.")
    project_add.add_argument("name")
    project_add.add_argument("--description", default="")
    project_add.add_argument("--priority", type=int, default=3)
    project_add.add_argument("--target-date")
    project_add.add_argument("--goal-id", action="append", default=[])
    project_add.add_argument("--task-id", action="append", default=[])
    project_add.add_argument("--now")
    project_list = project_subparsers.add_parser("list", help="List projects.")
    project_list.add_argument("--include-archived", action="store_true")
    milestone_add = project_subparsers.add_parser(
        "milestone-add", help="Add a project milestone."
    )
    milestone_add.add_argument("project_id")
    milestone_add.add_argument("title")
    milestone_add.add_argument("--target-date")
    milestone_add.add_argument("--now")
    milestone_update = project_subparsers.add_parser(
        "milestone-update", help="Update a milestone."
    )
    milestone_update.add_argument("project_id")
    milestone_update.add_argument("milestone_id")
    milestone_update.add_argument(
        "--status", choices=["pending", "in_progress", "completed"], required=True
    )
    milestone_update.add_argument("--now")
    project_progress = project_subparsers.add_parser(
        "progress", help="Record project progress."
    )
    project_progress.add_argument("project_id")
    project_progress.add_argument("percent", type=int)
    project_progress.add_argument("--note", default="")
    project_progress.add_argument("--correction", action="store_true")
    project_progress.add_argument("--now")
    project_archive = project_subparsers.add_parser(
        "archive", help="Archive a project."
    )
    project_archive.add_argument("project_id")
    project_archive.add_argument("--now")

    research_parser = subparsers.add_parser(
        "research", help="Work with the evidence-oriented research companion."
    )
    research_subparsers = research_parser.add_subparsers(
        dest="research_command", required=True
    )
    research_create = research_subparsers.add_parser("create")
    research_create.add_argument("title")
    research_create.add_argument("--objective", default="")
    research_create.add_argument("--question", default="")
    research_create.add_argument("--now")
    research_list = research_subparsers.add_parser("list")
    research_list.add_argument("--include-archived", action="store_true")
    research_show = research_subparsers.add_parser("show")
    research_show.add_argument("research_id")
    research_question = research_subparsers.add_parser("question-add")
    research_question.add_argument("research_id")
    research_question.add_argument("question")
    research_question.add_argument("--now")
    research_source = research_subparsers.add_parser("source-add")
    research_source.add_argument("research_id")
    research_source.add_argument(
        "--type",
        choices=["paper", "web", "book", "code", "dataset", "other"],
        required=True,
    )
    research_source.add_argument("--title", required=True)
    research_source.add_argument("--locator", default="")
    research_source.add_argument("--note", default="")
    research_source.add_argument("--now")
    research_note = research_subparsers.add_parser("note-add")
    research_note.add_argument("research_id")
    research_note.add_argument("text")
    research_note.add_argument("--source-id", action="append", default=[])
    research_note.add_argument("--tag", action="append", default=[])
    research_note.add_argument("--now")
    research_experiment = research_subparsers.add_parser("experiment-add")
    research_experiment.add_argument("research_id")
    research_experiment.add_argument("title")
    research_experiment.add_argument("--hypothesis", default="")
    research_experiment.add_argument("--method", default="")
    research_experiment.add_argument("--result", default="")
    research_experiment.add_argument(
        "--status",
        choices=["planned", "running", "completed", "blocked"],
        default="planned",
    )
    research_experiment.add_argument("--source-id", action="append", default=[])
    research_experiment.add_argument("--now")
    research_investigate = research_subparsers.add_parser("investigate")
    research_investigate.add_argument("research_id")
    research_investigate.add_argument("query")
    research_investigate.add_argument("--live-tools", action="store_true")
    research_investigate.add_argument("--now")
    for command_name in ("synthesize", "ask"):
        command = research_subparsers.add_parser(command_name)
        command.add_argument("research_id")
        if command_name == "ask":
            command.add_argument("question")
        command.add_argument("--llm", action="store_true")
        command.add_argument("--model-tier", choices=["simple", "complex"])
        command.add_argument("--now")
    research_archive = research_subparsers.add_parser("archive")
    research_archive.add_argument("research_id")
    research_archive.add_argument("--now")
    research_document_add = research_subparsers.add_parser("document-add")
    research_document_add.add_argument("research_id")
    research_document_add.add_argument("path")
    research_document_list = research_subparsers.add_parser("document-list")
    research_document_list.add_argument("research_id")
    research_document_show = research_subparsers.add_parser("document-show")
    research_document_show.add_argument("research_id")
    research_document_show.add_argument("document_id")
    research_document_remove = research_subparsers.add_parser("document-remove")
    research_document_remove.add_argument("research_id")
    research_document_remove.add_argument("document_id")
    research_document_reindex = research_subparsers.add_parser("document-reindex")
    research_document_reindex.add_argument("research_id")
    research_document_reindex.add_argument("document_id")
    research_document_search = research_subparsers.add_parser("document-search")
    research_document_search.add_argument("research_id")
    research_document_search.add_argument("query")
    research_document_search.add_argument("--limit", type=int, default=5)
    research_web_add = research_subparsers.add_parser("web-add")
    research_web_add.add_argument("research_id")
    research_web_add.add_argument("url")
    research_repo_index = research_subparsers.add_parser("repo-index")
    research_repo_index.add_argument("research_id")
    research_repo_index.add_argument("path")
    research_run = research_subparsers.add_parser("run")
    research_run.add_argument("research_id")
    research_run.add_argument("question")
    research_run.add_argument("--max-cycles", type=int, default=3)
    research_run.add_argument("--llm", action="store_true")
    research_run.add_argument("--model-tier", choices=["simple", "complex"])
    research_run.add_argument("--now")
    research_experiment_run = research_subparsers.add_parser("experiment-run")
    research_experiment_run.add_argument("research_id")
    research_experiment_run.add_argument("--cwd", required=True)
    research_experiment_run.add_argument("--allowed-root", required=True)
    research_experiment_run.add_argument(
        "--allow-executable", action="append", required=True
    )
    research_experiment_run.add_argument("--approve", action="store_true")
    research_experiment_run.add_argument("--timeout", type=float, default=30)
    research_experiment_run.add_argument("--command", nargs="+", required=True)

    suggestion_parser = subparsers.add_parser(
        "suggestion", help="Manage explainable suggestions."
    )
    suggestion_subparsers = suggestion_parser.add_subparsers(
        dest="suggestion_command", required=True
    )
    suggestion_list = suggestion_subparsers.add_parser(
        "list", help="List current suggestions."
    )
    suggestion_list.add_argument("--now")
    suggestion_list.add_argument("--limit", type=int, default=10)
    suggestion_list.add_argument("--llm", action="store_true")
    suggestion_list.add_argument("--model-tier", choices=["simple", "complex"])
    suggestion_list.add_argument("--live-tools", action="store_true")
    suggestion_refresh = suggestion_subparsers.add_parser(
        "refresh", help="Regenerate suggestions."
    )
    suggestion_refresh.add_argument("--now")
    suggestion_refresh.add_argument("--limit", type=int, default=10)
    suggestion_refresh.add_argument("--llm", action="store_true")
    suggestion_refresh.add_argument("--model-tier", choices=["simple", "complex"])
    suggestion_refresh.add_argument("--live-tools", action="store_true")
    suggestion_accept = suggestion_subparsers.add_parser(
        "accept", help="Accept a suggestion action."
    )
    suggestion_accept.add_argument("suggestion_id")
    suggestion_accept.add_argument("--approve", action="store_true")
    suggestion_accept.add_argument("--now")
    suggestion_dismiss = suggestion_subparsers.add_parser(
        "dismiss", help="Dismiss a suggestion."
    )
    suggestion_dismiss.add_argument("suggestion_id")
    suggestion_dismiss.add_argument("--now")

    replan_parser = subparsers.add_parser(
        "replan", help="Replan tasks around calendar constraints."
    )
    replan_subparsers = replan_parser.add_subparsers(
        dest="replan_command", required=True
    )
    replan_preview = replan_subparsers.add_parser(
        "preview", help="Preview a conflict-safe replan."
    )
    replan_preview.add_argument("--date", required=True)
    replan_preview.add_argument("--events-json", default="[]")
    replan_preview.add_argument("--calendar-unavailable", action="store_true")
    replan_preview.add_argument("--live-calendar", action="store_true")
    replan_preview.add_argument("--working-start", default="09:00")
    replan_preview.add_argument("--working-end", default="18:00")
    replan_preview.add_argument("--now")
    replan_apply = replan_subparsers.add_parser(
        "apply", help="Apply a fresh replan preview."
    )
    replan_apply.add_argument("--preview-json", required=True)
    replan_apply.add_argument("--events-json", default="[]")
    replan_apply.add_argument("--calendar-unavailable", action="store_true")
    replan_apply.add_argument("--live-calendar", action="store_true")
    replan_apply.add_argument("--now")

    plan_parser = subparsers.add_parser("plan", help="Create and inspect daily plans.")
    plan_parser.add_argument(
        "plan_command", choices=["day"], help="Create today's structured plan."
    )
    plan_parser.add_argument("--name", default="User")
    plan_parser.add_argument("--coach-mode", choices=COACH_MODES, default="gentle")
    plan_parser.add_argument("--llm", action="store_true")
    plan_parser.add_argument("--model-tier", choices=["simple", "complex"])
    plan_parser.add_argument("--show-prompt", action="store_true")
    plan_parser.add_argument(
        "--live-mcp", action="store_true", help="Run approved MCP planning tools."
    )
    plan_parser.add_argument(
        "--agents", action="store_true", help="Use bounded multi-agent coordination."
    )
    plan_parser.add_argument(
        "--now", help="Optional ISO timestamp for deterministic planning."
    )

    task_parser = subparsers.add_parser(
        "task", help="Inspect or update planned daily tasks."
    )
    task_subparsers = task_parser.add_subparsers(dest="task_command", required=True)
    task_list = task_subparsers.add_parser("list", help="List planned tasks.")
    task_list.add_argument("--date", help="Filter by YYYY-MM-DD plan date.")
    task_update = task_subparsers.add_parser(
        "update", help="Update task progress and reflection fields."
    )
    task_update.add_argument("task_id")
    task_update.add_argument("--status", choices=TASK_STATUSES)
    task_update.add_argument(
        "--blocker", help="Structured reason the task is blocked; empty text clears it."
    )
    task_update.add_argument(
        "--unresolved",
        action="append",
        default=[],
        help="Open item to carry into review; repeat as needed.",
    )
    task_update.add_argument("--note", help="Append a progress note.")

    review_parser = subparsers.add_parser(
        "review", help="Run proactive reminders or daily reflection."
    )
    review_parser.add_argument(
        "review_command",
        nargs="?",
        choices=["day"],
        help="Use `day` for evening daily review.",
    )
    review_parser.add_argument(
        "--name", default="User", help="User name for daily review."
    )
    review_parser.add_argument("--coach-mode", choices=COACH_MODES, default="gentle")
    review_parser.add_argument(
        "--llm", action="store_true", help="Use configured LLM for daily review."
    )
    review_parser.add_argument(
        "--agents", action="store_true", help="Use bounded multi-agent coordination."
    )
    review_parser.add_argument(
        "--model-tier",
        choices=["simple", "complex"],
        help="Model tier to use for LLM review generation. Defaults to configured tier.",
    )
    review_parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="Include the generated LLM prompt in JSON output.",
    )
    review_parser.add_argument(
        "--now",
        help="Optional ISO timestamp for deterministic review runs.",
    )

    briefing_parser = subparsers.add_parser(
        "briefing", help="Generate a morning life briefing."
    )
    briefing_parser.add_argument(
        "--name", default="User", help="User name for the greeting."
    )
    briefing_parser.add_argument("--weather", help="Optional weather summary.")
    briefing_parser.add_argument(
        "--llm", action="store_true", help="Use configured LLM for the briefing."
    )
    briefing_parser.add_argument(
        "--agents", action="store_true", help="Use bounded multi-agent coordination."
    )
    briefing_parser.add_argument(
        "--model-tier",
        choices=["simple", "complex"],
        help="Model tier to use for LLM generation. Defaults to configured tier.",
    )
    briefing_parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="Include the generated LLM prompt in JSON output.",
    )
    briefing_parser.add_argument(
        "--now",
        help="Optional ISO timestamp for deterministic briefing runs.",
    )
    briefing_parser.add_argument(
        "--live-tools",
        action="store_true",
        help="Fetch configured weather, calendar, and Todoist context.",
    )

    voice_parser = subparsers.add_parser(
        "voice", help="Run explicit local voice operations."
    )
    voice_subparsers = voice_parser.add_subparsers(
        dest="voice_command", required=True
    )
    voice_subparsers.add_parser("status", help="Show local voice configuration.")
    voice_record = voice_subparsers.add_parser(
        "record", help="Record a bounded WAV file."
    )
    voice_record.add_argument("output")
    voice_record.add_argument("--seconds", type=int, required=True)
    voice_transcribe = voice_subparsers.add_parser(
        "transcribe", help="Transcribe a local WAV file."
    )
    voice_transcribe.add_argument("input")
    voice_speak = voice_subparsers.add_parser(
        "speak", help="Speak or save text locally."
    )
    voice_speak.add_argument("text")
    voice_speak.add_argument("--output")
    voice_speak.add_argument(
        "--play", action=argparse.BooleanOptionalAction, default=None
    )
    voice_ask = voice_subparsers.add_parser(
        "ask", help="Transcribe and route a request through Nexus conversation."
    )
    voice_ask_source = voice_ask.add_mutually_exclusive_group(required=True)
    voice_ask_source.add_argument("--input")
    voice_ask_source.add_argument("--record-seconds", type=int)
    voice_ask.add_argument("--approve", action="store_true")
    voice_ask.add_argument("--llm", action="store_true")
    voice_ask.add_argument("--model-tier", choices=["simple", "complex"])
    voice_ask.add_argument("--show-intent", action="store_true")
    voice_ask.add_argument("--now")
    voice_ask.add_argument("--output")
    voice_ask.add_argument(
        "--play", action=argparse.BooleanOptionalAction, default=None
    )
    voice_briefing = voice_subparsers.add_parser(
        "briefing", help="Generate and narrate the normal Nexus briefing."
    )
    voice_briefing.add_argument("--weather")
    voice_briefing.add_argument("--llm", action="store_true")
    voice_briefing.add_argument("--agents", action="store_true")
    voice_briefing.add_argument("--model-tier", choices=["simple", "complex"])
    voice_briefing.add_argument("--show-prompt", action="store_true")
    voice_briefing.add_argument("--now")
    voice_briefing.add_argument("--live-tools", action="store_true")
    voice_briefing.add_argument("--output")
    voice_briefing.add_argument(
        "--play", action=argparse.BooleanOptionalAction, default=None
    )

    tool_parser = subparsers.add_parser("tool", help="Run permissioned external tools.")
    tool_subparsers = tool_parser.add_subparsers(dest="tool_command", required=True)
    weather_tool = tool_subparsers.add_parser("weather")
    weather_tool.add_argument("--location")
    calendar_tool = tool_subparsers.add_parser("calendar")
    calendar_tool.add_argument("--days", type=int, default=2)
    calendar_tool.add_argument("--now")
    todo_tool = tool_subparsers.add_parser("todo")
    todo_tool.add_argument("--limit", type=int, default=20)
    github_tool = tool_subparsers.add_parser("github")
    github_tool.add_argument("--repo")
    github_tool.add_argument("--limit", type=int, default=10)
    notion_tool = tool_subparsers.add_parser("notion")
    notion_tool.add_argument("--query", default="")
    notion_tool.add_argument("--limit", type=int, default=10)
    literature_tool = tool_subparsers.add_parser("literature")
    literature_tool.add_argument("--query", required=True)
    literature_tool.add_argument("--limit", type=int, default=5)
    email_tool = tool_subparsers.add_parser("email")
    email_tool.add_argument("--limit", type=int, default=10)
    email_tool.add_argument(
        "--all", action="store_true", help="Include already-read messages."
    )
    files_tool = tool_subparsers.add_parser("files")
    files_tool.add_argument("files_command", choices=["list", "read", "search"])
    files_tool.add_argument("path")
    files_tool.add_argument("--query")
    files_tool.add_argument("--max-bytes", type=int, default=65536)
    audit_tool = tool_subparsers.add_parser("audit")
    audit_tool.add_argument("--limit", type=int, default=50)

    mcp_parser = subparsers.add_parser(
        "mcp", help="Discover and call permissioned MCP tools."
    )
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command", required=True)
    mcp_subparsers.add_parser("servers", help="List configured MCP servers.")
    mcp_tools = mcp_subparsers.add_parser("tools", help="Discover tools from a server.")
    mcp_tools.add_argument("server")
    mcp_call = mcp_subparsers.add_parser("call", help="Call one MCP tool.")
    mcp_call.add_argument("server")
    mcp_call.add_argument("tool")
    mcp_call.add_argument("--arguments", default="{}", help="JSON object arguments.")
    mcp_call.add_argument(
        "--approve", action="store_true", help="Approve one ask-policy call."
    )
    mcp_audit = mcp_subparsers.add_parser(
        "audit", help="Show secret-safe MCP audit events."
    )
    mcp_audit.add_argument("--limit", type=int, default=50)
    mcp_server_parser = subparsers.add_parser(
        "mcp-server", help="Expose Nexus as a permissioned local MCP server."
    )
    mcp_server_subparsers = mcp_server_parser.add_subparsers(
        dest="mcp_server_command", required=True
    )
    mcp_server_stdio = mcp_server_subparsers.add_parser(
        "stdio", help="Run the Nexus MCP server over standard input/output."
    )
    mcp_server_stdio.add_argument(
        "--approve-tool",
        action="append",
        default=[],
        help="Approve one ask-policy tool for this server session.",
    )
    agent_parser = subparsers.add_parser("agent", help="Inspect multi-agent runs.")
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command", required=True)
    agent_runs = agent_subparsers.add_parser("runs", help="List recent agent runs.")
    agent_runs.add_argument("--limit", type=int, default=20)
    agent_show = agent_subparsers.add_parser("show", help="Show one agent run.")
    agent_show.add_argument("run_id")
    config_parser = subparsers.add_parser(
        "config", help="Manage local Nexus configuration."
    )
    config_subparsers = config_parser.add_subparsers(
        dest="config_command", required=True
    )
    llm_parser = config_subparsers.add_parser(
        "llm", help="Manage local LLM configuration."
    )
    llm_subparsers = llm_parser.add_subparsers(dest="llm_command", required=True)

    llm_set = llm_subparsers.add_parser(
        "set", help="Save local LLM provider/model configuration."
    )
    llm_set.add_argument(
        "--provider", choices=["openai", "deepseek", "custom"], required=True
    )
    llm_set.add_argument(
        "--api-key", required=True, help="API key saved only to local ignored config."
    )
    llm_set.add_argument(
        "--base-url",
        help="OpenAI-compatible base URL. Uses provider preset by default.",
    )
    llm_set.add_argument("--simple-model", help="Cheap/fast model for simple tasks.")
    llm_set.add_argument("--complex-model", help="Stronger model for complex tasks.")
    llm_set.add_argument(
        "--default-tier", choices=["simple", "complex"], default="simple"
    )
    llm_set.add_argument("--timeout-seconds", type=int, default=30)

    llm_subparsers.add_parser(
        "show", help="Show local LLM configuration with masked API key."
    )

    voice_config_parser = config_subparsers.add_parser(
        "voice", help="Manage local voice configuration."
    )
    voice_config_subparsers = voice_config_parser.add_subparsers(
        dest="voice_config_command", required=True
    )
    voice_set = voice_config_subparsers.add_parser(
        "set", help="Save local voice configuration."
    )
    voice_set.add_argument("--enable", action="store_true", default=None)
    voice_set.add_argument("--model")
    voice_set.add_argument("--language")
    voice_set.add_argument("--voice")
    voice_set.add_argument("--sample-rate", type=int)
    voice_set.add_argument("--max-record-seconds", type=int)
    voice_set.add_argument("--max-audio-mib", type=int)
    voice_set.add_argument(
        "--play", action=argparse.BooleanOptionalAction, default=None
    )
    voice_config_subparsers.add_parser("show", help="Show local voice configuration.")
    voice_config_subparsers.add_parser(
        "disable", help="Disable local voice operations."
    )

    embedding_parser = config_subparsers.add_parser(
        "embedding", help="Manage semantic RAG configuration."
    )
    embedding_subparsers = embedding_parser.add_subparsers(
        dest="embedding_command", required=True
    )

    embedding_set = embedding_subparsers.add_parser(
        "set", help="Save embedding and Qdrant configuration."
    )
    embedding_set.add_argument(
        "--provider",
        choices=["local_sparse", "fastembed", "openai", "custom"],
        required=True,
    )
    embedding_set.add_argument("--model")
    embedding_set.add_argument(
        "--api-key", help="Required for hosted embedding providers."
    )
    embedding_set.add_argument("--base-url", help="OpenAI-compatible API base URL.")
    embedding_set.add_argument(
        "--qdrant-url",
        help="Remote Qdrant URL; local persistence is used when omitted.",
    )
    embedding_set.add_argument("--qdrant-api-key")
    embedding_set.add_argument("--collection", default="nexus_memories")
    embedding_set.add_argument("--timeout-seconds", type=int, default=30)
    embedding_subparsers.add_parser(
        "show", help="Show semantic RAG configuration with masked secrets."
    )

    tool_config_parser = config_subparsers.add_parser(
        "tool", help="Manage external tool configuration."
    )
    tool_config_subparsers = tool_config_parser.add_subparsers(
        dest="tool_config_command", required=True
    )
    tool_set = tool_config_subparsers.add_parser(
        "set", help="Configure and enable one tool."
    )
    tool_set.add_argument(
        "tool_name",
        choices=[
            "weather",
            "calendar",
            "todo",
            "github",
            "notion",
            "email",
            "filesystem",
            "literature",
        ],
    )
    tool_set.add_argument("--location")
    tool_set.add_argument("--calendar-url")
    tool_set.add_argument("--token")
    tool_set.add_argument("--repo")
    tool_set.add_argument("--host")
    tool_set.add_argument("--port", type=int)
    tool_set.add_argument("--username")
    tool_set.add_argument("--password")
    tool_set.add_argument("--mailbox")
    tool_set.add_argument("--root", action="append", dest="roots")
    tool_set.add_argument("--timeout-seconds", type=int)
    tool_set.add_argument("--mailto")
    tool_disable = tool_config_subparsers.add_parser(
        "disable", help="Disable a configured tool."
    )
    tool_disable.add_argument(
        "tool_name",
        choices=[
            "weather",
            "calendar",
            "todo",
            "github",
            "notion",
            "email",
            "filesystem",
            "literature",
        ],
    )
    tool_config_subparsers.add_parser(
        "show", help="Show tool configuration with masked secrets."
    )

    mcp_config_parser = config_subparsers.add_parser(
        "mcp", help="Manage MCP server configuration."
    )
    mcp_config_subparsers = mcp_config_parser.add_subparsers(
        dest="mcp_config_command", required=True
    )
    mcp_add = mcp_config_subparsers.add_parser(
        "add", help="Add or replace an MCP server."
    )
    mcp_add.add_argument("server_name")
    mcp_add.add_argument(
        "--transport", choices=["stdio", "streamable_http"], required=True
    )
    mcp_add.add_argument("--command", dest="server_command")
    mcp_add.add_argument("--arg", action="append", default=[], dest="server_args")
    mcp_add.add_argument("--url")
    mcp_add.add_argument("--header", action="append", default=[])
    mcp_add.add_argument("--env", action="append", default=[])
    mcp_add.add_argument("--timeout-seconds", type=int, default=30)
    mcp_add.add_argument("--max-retries", type=int, default=1)
    mcp_disable = mcp_config_subparsers.add_parser("disable")
    mcp_disable.add_argument("server_name")
    mcp_remove = mcp_config_subparsers.add_parser("remove")
    mcp_remove.add_argument("server_name")
    mcp_policy = mcp_config_subparsers.add_parser("policy")
    mcp_policy.add_argument("server_name")
    mcp_policy.add_argument("tool")
    mcp_policy.add_argument("policy", choices=["deny", "ask", "allow"])
    mcp_planning = mcp_config_subparsers.add_parser("planning-tool")
    mcp_planning.add_argument("server_name")
    mcp_planning.add_argument("tool")
    mcp_planning.add_argument("--arguments", default="{}")
    mcp_config_subparsers.add_parser("show")
    profile_parser = config_subparsers.add_parser(
        "profile", help="Manage the local user profile."
    )
    profile_subparsers = profile_parser.add_subparsers(
        dest="profile_command", required=True
    )
    profile_subparsers.add_parser("show")
    profile_set = profile_subparsers.add_parser("set")
    profile_set.add_argument("--name")
    profile_set.add_argument("--timezone")

    runtime_config_parser = config_subparsers.add_parser(
        "runtime", help="Manage proactive runtime configuration."
    )
    runtime_config_subparsers = runtime_config_parser.add_subparsers(
        dest="runtime_config_command", required=True
    )
    runtime_config_subparsers.add_parser("show")
    runtime_set = runtime_config_subparsers.add_parser("set")
    runtime_set.add_argument("--job", action="append", choices=RUNTIME_JOB_NAMES)
    runtime_set.add_argument("--clear-jobs", action="store_true")
    runtime_set.add_argument("--morning-time")
    runtime_set.add_argument("--evening-time")
    runtime_set.add_argument("--reminder-time")
    runtime_set.add_argument("--grace-minutes", type=int)
    runtime_set.add_argument("--poll-interval-seconds", type=int)
    runtime_set.add_argument("--quiet-hours", nargs=2, metavar=("START", "END"))
    runtime_set.add_argument("--clear-quiet-hours", action="store_true")
    runtime_set.add_argument(
        "--inbox", dest="inbox_enabled", action=argparse.BooleanOptionalAction
    )
    runtime_set.add_argument(
        "--console", dest="console_enabled", action=argparse.BooleanOptionalAction
    )
    runtime_set.add_argument("--use-llm", action=argparse.BooleanOptionalAction)
    runtime_set.add_argument("--live-tools", action=argparse.BooleanOptionalAction)
    runtime_set.add_argument("--agents", action=argparse.BooleanOptionalAction)
    runtime_set.add_argument("--webhook-url")
    runtime_set.add_argument("--clear-webhook", action="store_true")
    runtime_set.add_argument("--coach-mode", choices=COACH_MODES)

    runtime_parser = subparsers.add_parser(
        "runtime", help="Inspect and run the proactive scheduler."
    )
    runtime_subparsers = runtime_parser.add_subparsers(
        dest="runtime_command", required=True
    )
    runtime_subparsers.add_parser("status")
    runtime_tick = runtime_subparsers.add_parser("tick")
    runtime_tick.add_argument("--now")
    runtime_run = runtime_subparsers.add_parser("run")
    runtime_run.add_argument("job", choices=RUNTIME_JOB_NAMES)
    runtime_run.add_argument("--now")
    runtime_start = runtime_subparsers.add_parser("start")
    runtime_start.add_argument("--max-ticks", type=int)

    notifications_parser = subparsers.add_parser(
        "notifications", help="Inspect and flush proactive notifications."
    )
    notifications_subparsers = notifications_parser.add_subparsers(
        dest="notifications_command", required=True
    )
    notifications_list = notifications_subparsers.add_parser("list")
    notifications_list.add_argument("--limit", type=int, default=50)
    notifications_subparsers.add_parser("flush")

    dashboard_parser = subparsers.add_parser(
        "dashboard", help="Inspect or serve the local life dashboard."
    )
    dashboard_subparsers = dashboard_parser.add_subparsers(
        dest="dashboard_command", required=True
    )
    dashboard_subparsers.add_parser("snapshot")
    dashboard_serve = dashboard_subparsers.add_parser("serve")
    dashboard_serve.add_argument("--host", default="127.0.0.1")
    dashboard_serve.add_argument("--port", type=int, default=8765)

    automation_parser = subparsers.add_parser(
        "automation", help="Manage named permissioned automations."
    )
    automation_subparsers = automation_parser.add_subparsers(
        dest="automation_command", required=True
    )
    automation_subparsers.add_parser("list")
    automation_set = automation_subparsers.add_parser("set")
    automation_set.add_argument("name")
    automation_set.add_argument("--definition", required=True)
    automation_remove = automation_subparsers.add_parser("remove")
    automation_remove.add_argument("name")
    automation_run = automation_subparsers.add_parser("run")
    automation_run.add_argument("name")
    automation_run.add_argument("--approve", action="store_true")
    automation_audit = automation_subparsers.add_parser("audit")
    automation_audit.add_argument("--limit", type=int, default=50)
    return parser


def parse_json_object(value: str) -> dict[str, object]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Arguments must be valid JSON: {exc.msg}.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Arguments JSON must be an object.")
    return parsed


def parse_pairs(values: list[str], label: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"{label} must use KEY=VALUE format.")
        key, item = value.split("=", 1)
        if not key:
            raise ValueError(f"{label} key cannot be empty.")
        parsed[key] = item
    return parsed


def print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def memory_mutation_status(result: dict[str, object]) -> str:
    sync = result.get("index_sync")
    if isinstance(sync, dict) and sync.get("error"):
        return "partial"
    return "ok"


class _LazyRecentAdapter:
    def __init__(self, factory: Callable[[], Any], method: str) -> None:
        self._factory = factory
        self._method = method

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        source = self._factory()
        reader = getattr(source, self._method)
        return reader(limit)


def _error_exit(code: str, error: str, exit_code: int) -> None:
    print_json({"status": "error", "code": code, "error": error})
    raise SystemExit(exit_code)


def _parse_optional_now(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        _error_exit("invalid_datetime", "now must be an ISO timestamp.", 2)
        raise AssertionError("unreachable") from exc


def _build_notification_center(
    profile: ProfileSettings,
    runtime: RuntimeSettings,
) -> NotificationCenter:
    return NotificationCenter(
        nexus_home() / "notifications.jsonl",
        runtime,
        profile,
    )


def _build_scheduler() -> ProactiveScheduler:
    profile, runtime = load_runtime_settings()
    store = JsonStore.from_env()
    embedding_settings = load_embedding_settings()
    retriever = build_memory_retriever(embedding_settings, nexus_home())
    llm = None
    if runtime.use_llm:
        llm_config = LLMConfig.from_env()
        if llm_config.is_configured:
            llm = OpenAICompatibleLLM(llm_config)
    service = NexusService(store, llm=llm, memory_retriever=retriever)
    notifications = _build_notification_center(profile, runtime)

    tool_manager = None
    if runtime.live_tools:
        tool_manager = build_tool_manager(load_tool_settings(), nexus_home())

    orchestrator = None
    if runtime.agents:
        mcp_manager = build_mcp_manager(load_mcp_settings(), nexus_home())
        orchestrator = AgentOrchestrator(
            service,
            mcp_manager=mcp_manager,
            trace_store=AgentTraceStore(nexus_home() / "agent_runs.jsonl"),
        )
    return ProactiveScheduler(
        store,
        service,
        notifications,
        profile,
        runtime,
        tool_manager=tool_manager,
        orchestrator=orchestrator,
    )


def _build_automation_manager() -> AutomationManager:
    home = nexus_home()
    return AutomationManager(
        load_automation_settings(),
        home,
        JsonStore.from_env(),
        tool_manager=build_tool_manager(load_tool_settings(), home),
    )


def _dashboard_settings() -> dict[str, Any]:
    profile, runtime = load_runtime_settings()
    return {
        "profile": profile.masked(),
        "runtime": runtime.masked(),
        "llm": load_llm_settings().masked(),
        "embedding": load_embedding_settings().masked(),
        "tools": masked_tool_settings(load_tool_settings()),
        "mcp": masked_mcp_settings(load_mcp_settings()),
        "automations": masked_automation_settings(load_automation_settings()),
    }


def _dashboard_notification_center() -> NotificationCenter:
    profile, runtime = load_runtime_settings()
    return _build_notification_center(profile, runtime)


def _dashboard_tool_manager() -> Any:
    return build_tool_manager(load_tool_settings(), nexus_home())


def _dashboard_mcp_manager() -> Any:
    return build_mcp_manager(load_mcp_settings(), nexus_home())


def _dashboard_calendar_events(plan_date: str) -> list[dict[str, Any]] | None:
    profile, _runtime = load_runtime_settings()
    local_start = datetime.combine(
        date.fromisoformat(plan_date), time.min, ZoneInfo(profile.timezone)
    )
    try:
        result = _dashboard_tool_manager().execute(
            "calendar", "read", days=2, now=local_start.isoformat()
        )
    except ToolError:
        return None
    events = result.data.get("events")
    return events if isinstance(events, list) else None


def _build_dashboard_snapshot() -> DashboardSnapshot:
    raw_profile = load_local_config().get("profile", {})
    if not isinstance(raw_profile, dict):
        raise ValueError("Profile configuration must be an object.")
    profile = profile_settings_from_mapping(dict(raw_profile))
    store = JsonStore.from_env()
    home = nexus_home()
    return DashboardSnapshot(
        state_source=store.load,
        notifications=_LazyRecentAdapter(_dashboard_notification_center, "recent"),
        tool_audit=_LazyRecentAdapter(_dashboard_tool_manager, "audit_events"),
        mcp_audit=_LazyRecentAdapter(_dashboard_mcp_manager, "audit_events"),
        agent_traces=AgentTraceStore(home / "agent_runs.jsonl"),
        automation_audit=_LazyRecentAdapter(_build_automation_manager, "audit_events"),
        scheduler_status=lambda: _build_scheduler().scheduler_status(),
        settings=_dashboard_settings,
        timezone=profile.timezone,
    )


def _build_dashboard_server(*, host: str, port: int) -> DashboardServer:
    profile, _runtime = load_runtime_settings()
    actions = DashboardActions(
        NexusService(JsonStore.from_env()),
        timezone=profile.timezone,
        calendar_events=_dashboard_calendar_events,
    )
    return DashboardServer(
        _build_dashboard_snapshot(),
        actions=actions,
        host=host,
        port=port,
    )


def _serve_dashboard(server: DashboardServer) -> None:
    try:
        server.start()
        print_json({"status": "serving", "url": server.url})
        stopped = threading.Event()
        while server.is_running:
            stopped.wait(3600)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


def _runtime_patch_values(args: argparse.Namespace) -> dict[str, Any]:
    if args.clear_jobs and args.job:
        raise ValueError("--job and --clear-jobs cannot be used together.")
    if args.clear_quiet_hours and args.quiet_hours:
        raise ValueError(
            "--quiet-hours and --clear-quiet-hours cannot be used together."
        )
    if args.clear_webhook and args.webhook_url is not None:
        raise ValueError("--webhook-url and --clear-webhook cannot be used together.")

    changes: dict[str, Any] = {}
    if args.clear_jobs:
        changes["enabled_jobs"] = ()
    elif args.job is not None:
        changes["enabled_jobs"] = tuple(args.job)
    for argument, field in (
        (args.morning_time, "morning_time"),
        (args.evening_time, "evening_time"),
        (args.reminder_time, "reminder_time"),
        (args.grace_minutes, "grace_minutes"),
        (args.poll_interval_seconds, "poll_interval_seconds"),
        (args.inbox_enabled, "inbox_enabled"),
        (args.console_enabled, "console_enabled"),
        (args.use_llm, "use_llm"),
        (args.live_tools, "live_tools"),
        (args.agents, "agents"),
        (args.coach_mode, "coach_mode"),
    ):
        if argument is not None:
            changes[field] = argument
    if args.clear_quiet_hours:
        changes["quiet_hours_start"] = None
        changes["quiet_hours_end"] = None
    elif args.quiet_hours is not None:
        changes["quiet_hours_start"], changes["quiet_hours_end"] = args.quiet_hours
    if args.clear_webhook:
        changes["webhook_url"] = None
    elif args.webhook_url is not None:
        changes["webhook_url"] = args.webhook_url
    return changes


def _briefing_result(
    args: argparse.Namespace,
    *,
    user_name: str,
    now: datetime | None,
    service: NexusService,
    store: JsonStore,
    retriever: Any,
    tool_manager: Any,
    mcp_manager: Any,
    agent_traces: AgentTraceStore,
) -> dict[str, Any]:
    live_context = tool_manager.briefing_context(now) if args.live_tools else None
    if args.llm:
        config = LLMConfig.from_env(model_tier=args.model_tier)
        llm = OpenAICompatibleLLM(config) if config.is_configured else None
        service = NexusService(store, llm=llm, memory_retriever=retriever)
    if args.agents:
        orchestrator = AgentOrchestrator(
            service, mcp_manager=mcp_manager, trace_store=agent_traces
        )
        return orchestrator.run_briefing(
            user_name=user_name,
            weather=args.weather,
            now=now,
            use_llm=args.llm,
            external_context=live_context,
        )
    return service.daily_briefing(
        user_name,
        args.weather,
        now,
        args.llm,
        args.show_prompt,
        external_context=live_context,
    )


def _voice_config_values(args: argparse.Namespace) -> dict[str, Any]:
    current = load_voice_settings(env={})
    max_audio_bytes = (
        current.max_audio_bytes
        if args.max_audio_mib is None
        else args.max_audio_mib * 1024 * 1024
    )
    return {
        "enabled": current.enabled if args.enable is None else args.enable,
        "transcription_provider": current.transcription_provider,
        "transcription_model": (
            current.transcription_model if args.model is None else args.model
        ),
        "synthesis_provider": current.synthesis_provider,
        "voice": current.voice if args.voice is None else args.voice,
        "language": current.language if args.language is None else args.language,
        "sample_rate": (
            current.sample_rate if args.sample_rate is None else args.sample_rate
        ),
        "max_record_seconds": (
            current.max_record_seconds
            if args.max_record_seconds is None
            else args.max_record_seconds
        ),
        "max_audio_bytes": max_audio_bytes,
        "play_audio": current.play_audio if args.play is None else args.play,
    }


def _dispatch_voice(args: argparse.Namespace) -> bool:
    is_voice_config = args.command == "config" and args.config_command == "voice"
    if not is_voice_config and args.command != "voice":
        return False

    try:
        if is_voice_config:
            if args.voice_config_command == "show":
                print_json({"voice": load_voice_settings().masked()})
                return True
            if args.voice_config_command == "disable":
                settings, path = disable_voice_settings()
            else:
                settings, path = update_voice_settings(**_voice_config_values(args))
            print_json(
                {
                    "status": "ok",
                    "path": str(Path(path).expanduser().resolve(strict=False)),
                    "voice": settings.masked(),
                }
            )
            return True

        settings = load_voice_settings()
        if args.voice_command == "status":
            print_json(
                {
                    "status": "ok",
                    "voice": settings.masked(),
                    "providers": voice_provider_availability(settings),
                }
            )
            return True
        if not settings.enabled:
            raise VoiceConfigurationError("Voice support is disabled.")
        if (
            args.voice_command == "ask"
            and args.record_seconds is not None
            and not 1 <= args.record_seconds <= settings.max_record_seconds
        ):
            raise ValueError(
                "record-seconds must be between 1 and "
                f"{settings.max_record_seconds}."
            )

        recorder, transcriber, synthesizer = build_voice_providers(settings)
        if args.voice_command == "record":
            if not 1 <= args.seconds <= settings.max_record_seconds:
                raise ValueError(
                    "seconds must be between 1 and "
                    f"{settings.max_record_seconds}."
                )
            output_path = Path(args.output).expanduser().resolve(strict=False)
            if output_path.suffix.lower() != ".wav":
                raise ValueError("record output must use a WAV suffix.")
            if not output_path.parent.is_dir():
                raise ValueError("record output parent must exist.")
            recorded = recorder.record(
                output_path, seconds=args.seconds, sample_rate=settings.sample_rate
            )
            print_json(
                {
                    "status": "ok",
                    "output_path": str(Path(recorded).resolve(strict=False)),
                }
            )
            return True
        if args.voice_command == "transcribe":
            audio_path = validate_audio_file(
                Path(args.input),
                max_bytes=settings.max_audio_bytes,
                max_seconds=settings.max_record_seconds,
            )
            language = None if settings.language == "auto" else settings.language
            print_json(
                {
                    "transcript": transcriber.transcribe(
                        audio_path, language=language
                    ).to_dict()
                }
            )
            return True
        if args.voice_command == "speak":
            output_path = (
                Path(args.output).expanduser().resolve(strict=False)
                if args.output is not None
                else None
            )
            play = settings.play_audio if args.play is None else args.play
            speech = synthesizer.synthesize(
                args.text,
                voice=settings.voice,
                output_path=output_path,
                play=play,
            )
            print_json({"speech": speech.to_dict()})
            return True

        profile, _runtime = load_runtime_settings()
        store = JsonStore.from_env()
        embedding_settings = load_embedding_settings()
        retriever = build_memory_retriever(embedding_settings, nexus_home())
        llm = None
        if args.voice_command == "ask" and args.llm:
            llm_config = LLMConfig.from_env(model_tier=args.model_tier)
            llm = (
                OpenAICompatibleLLM(llm_config)
                if llm_config.is_configured
                else None
            )
        service = NexusService(store, llm=llm, memory_retriever=retriever)
        if args.voice_command == "ask":
            conversation = ConversationService(
                service, timezone=profile.timezone, llm=service.llm
            )
            voice = VoiceService(
                settings=settings,
                recorder=recorder,
                transcriber=transcriber,
                synthesizer=synthesizer,
                conversation=conversation,
            )
            result = voice.ask(
                audio_path=Path(args.input) if args.input is not None else None,
                record_seconds=args.record_seconds,
                approved=args.approve,
                use_llm=args.llm,
                show_intent=args.show_intent,
                now=_parse_optional_now(args.now),
                output_path=Path(args.output) if args.output is not None else None,
                play=args.play,
            )
            print_json(result)
            return True

        now = _parse_optional_now(args.now) or datetime.now(
            ZoneInfo(profile.timezone)
        )
        tool_manager = build_tool_manager(load_tool_settings(), nexus_home())
        mcp_manager = build_mcp_manager(load_mcp_settings(), nexus_home())
        briefing = _briefing_result(
            args,
            user_name=profile.display_name,
            now=now,
            service=service,
            store=store,
            retriever=retriever,
            tool_manager=tool_manager,
            mcp_manager=mcp_manager,
            agent_traces=AgentTraceStore(nexus_home() / "agent_runs.jsonl"),
        )
        voice = VoiceService(
            settings=settings,
            recorder=recorder,
            transcriber=transcriber,
            synthesizer=synthesizer,
            conversation=None,
        )
        print_json(
            voice.narrate_briefing(
                briefing,
                output_path=Path(args.output) if args.output is not None else None,
                play=args.play,
            )
        )
    except VoiceConfigurationError as exc:
        print_json({"status": "error", "error": str(exc)})
        raise SystemExit(2) from exc
    except VoiceError as exc:
        print_json({"status": "error", "error": str(exc)})
        raise SystemExit(1) from exc
    except (TypeError, ValueError) as exc:
        _error_exit("invalid_voice_config", str(exc), 2)
    return True


def _dispatch_phase10(args: argparse.Namespace) -> bool:
    if args.command == "config" and args.config_command == "profile":
        try:
            if args.profile_command == "show":
                profile, _runtime = load_runtime_settings()
                print_json({"profile": profile.masked()})
                return True
            changes = {}
            if args.name is not None:
                changes["display_name"] = args.name
            if args.timezone is not None:
                changes["timezone"] = args.timezone
            settings, path = patch_profile_settings(changes)
        except (TypeError, ValueError) as exc:
            _error_exit("invalid_profile_config", str(exc), 2)
        print_json({"status": "ok", "path": str(path), "profile": settings.masked()})
        return True

    if args.command == "config" and args.config_command == "runtime":
        try:
            if args.runtime_config_command == "show":
                _profile, runtime = load_runtime_settings()
                print_json({"runtime": runtime.masked()})
                return True
            changes = _runtime_patch_values(args)
            settings, path = patch_runtime_settings(changes)
        except (TypeError, ValueError) as exc:
            _error_exit("invalid_runtime_config", str(exc), 2)
        print_json({"status": "ok", "path": str(path), "runtime": settings.masked()})
        return True

    if args.command == "runtime":
        try:
            scheduler = _build_scheduler()
            if args.runtime_command == "status":
                print_json({"status": "ok", "scheduler": scheduler.scheduler_status()})
            elif args.runtime_command == "tick":
                print_json(
                    {
                        "status": "ok",
                        "outcomes": scheduler.tick(_parse_optional_now(args.now)),
                    }
                )
            elif args.runtime_command == "run":
                print_json(
                    {
                        "status": "ok",
                        "result": scheduler.run_job(
                            args.job, _parse_optional_now(args.now)
                        ),
                    }
                )
            else:
                try:
                    result = scheduler.run_forever(max_ticks=args.max_ticks)
                except KeyboardInterrupt:
                    print_json(
                        {
                            "status": "stopped",
                            "result": {"reason": "keyboard_interrupt"},
                        }
                    )
                    return True
                print_json({"status": "ok", "result": result})
        except (TypeError, ValueError) as exc:
            _error_exit("invalid_runtime_config", str(exc), 2)
        except Exception:
            _error_exit("runtime_execution_failed", "Runtime execution failed.", 1)
        return True

    if args.command == "notifications":
        try:
            profile, runtime = load_runtime_settings()
            notifications = _build_notification_center(profile, runtime)
            if args.notifications_command == "list":
                if args.limit < 1 or args.limit > 200:
                    raise ValueError("limit must be between 1 and 200.")
                print_json({"notifications": notifications.recent(args.limit)})
            else:
                print_json(
                    {
                        "status": "ok",
                        "notifications": notifications.flush_deferred(),
                    }
                )
        except (TypeError, ValueError) as exc:
            _error_exit("invalid_runtime_config", str(exc), 2)
        except Exception:
            _error_exit(
                "notification_operation_failed", "Notification operation failed.", 1
            )
        return True

    if args.command == "dashboard":
        try:
            if args.dashboard_command == "snapshot":
                print_json(_build_dashboard_snapshot().build())
            else:
                server = _build_dashboard_server(host=args.host, port=args.port)
                _serve_dashboard(server)
        except ValueError as exc:
            code = (
                "unsafe_dashboard_bind"
                if "loopback" in str(exc).casefold()
                else "invalid_dashboard_config"
            )
            _error_exit(code, str(exc), 2)
        except Exception:
            _error_exit("dashboard_failed", "Dashboard operation failed.", 1)
        return True

    if args.command == "automation":
        try:
            if args.automation_command == "list":
                print_json(
                    {
                        "automations": masked_automation_settings(
                            load_automation_settings()
                        )
                    }
                )
                return True
            if args.automation_command == "set":
                try:
                    definition = parse_json_object(args.definition)
                except ValueError as exc:
                    _error_exit("invalid_automation_config", str(exc), 2)
                settings, _path = upsert_automation(args.name, definition)
                print_json(
                    {
                        "status": "ok",
                        "automations": masked_automation_settings(settings),
                    }
                )
                return True
            if args.automation_command == "remove":
                settings, _path = remove_automation(args.name)
                print_json(
                    {
                        "status": "ok",
                        "automations": masked_automation_settings(settings),
                    }
                )
                return True
            manager = _build_automation_manager()
            if args.automation_command == "audit":
                if args.limit < 1 or args.limit > 1000:
                    raise AutomationConfigurationError(
                        "Audit limit must be between 1 and 1000."
                    )
                print_json({"events": manager.audit_events(args.limit)})
                return True
            print_json(
                {
                    "status": "ok",
                    "result": manager.run(args.name, approved=args.approve),
                }
            )
        except AutomationConfigurationError as exc:
            _error_exit(exc.code, str(exc), 2)
        except (AutomationPermissionError, AutomationExecutionError) as exc:
            _error_exit(exc.code, str(exc), 1)
        except AutomationError as exc:
            _error_exit(exc.code, str(exc), 1)
        return True

    return False


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if _dispatch_voice(args):
        return
    if _dispatch_phase10(args):
        return
    store = JsonStore.from_env()
    embedding_settings = load_embedding_settings()
    retriever = build_memory_retriever(embedding_settings, nexus_home())
    service = NexusService(store, memory_retriever=retriever)

    if args.command == "mcp-server":
        unknown = set(args.approve_tool) - set(NEXUS_MCP_TOOL_NAMES)
        if unknown:
            parser.error(f"Unknown Nexus MCP tool: {sorted(unknown)[0]}")
        try:
            profile, _runtime = load_runtime_settings()
            tools = NexusMCPTools(
                service,
                policies=load_nexus_mcp_server_policies(),
                approvals=args.approve_tool,
                timezone=profile.timezone,
            )
        except ValueError as exc:
            parser.error(str(exc))
        run_stdio_server(tools)
        return

    if args.command == "ask":
        try:
            now = datetime.fromisoformat(args.now) if args.now else None
            profile, _runtime = load_runtime_settings()
            if args.llm:
                config = LLMConfig.from_env(model_tier=args.model_tier)
                llm = OpenAICompatibleLLM(config) if config.is_configured else None
                service = NexusService(store, llm=llm, memory_retriever=retriever)
            result = service.ask(
                args.text,
                timezone=profile.timezone,
                approved=args.approve,
                use_llm=args.llm,
                show_intent=args.show_intent,
                now=now,
            )
            print_json(result)
        except (TypeError, ValueError) as exc:
            _error_exit("invalid_conversation", str(exc), 2)
        return
    if args.command == "habit":
        try:
            profile, _runtime = load_runtime_settings()
            timezone = profile.timezone
            now = (
                datetime.fromisoformat(args.now) if getattr(args, "now", None) else None
            )
            if args.habit_command == "add":
                if args.cadence == "weekdays" and not args.weekday:
                    raise ValueError(
                        "weekdays cadence requires at least one --weekday."
                    )
                habit = service.add_habit(
                    args.name,
                    args.description,
                    args.cadence,
                    tuple(args.weekday),
                    args.target_count,
                    args.goal_id,
                    now=now,
                    timezone=timezone,
                )
                print_json({"status": "ok", "habit": habit})
            elif args.habit_command == "list":
                print_json(
                    {
                        "habits": service.list_habits(
                            now=now,
                            include_archived=args.include_archived,
                            timezone=timezone,
                        )
                    }
                )
            elif args.habit_command == "check-in":
                current = now or datetime.now()
                local_date = args.date or current.date().isoformat()
                result = service.check_in_habit(
                    args.habit_id,
                    local_date,
                    args.count,
                    args.note,
                    now=now,
                    timezone=timezone,
                )
                print_json(
                    {
                        "status": "ok",
                        "habit": {**result["habit"], "summary": result["summary"]},
                    }
                )
            else:
                habit = service.archive_habit(args.habit_id, now=now, timezone=timezone)
                print_json({"status": "ok", "habit": habit})
        except (TypeError, ValueError) as exc:
            _error_exit("invalid_habit", str(exc), 2)
        return

    if args.command == "project":
        try:
            now = (
                datetime.fromisoformat(args.now) if getattr(args, "now", None) else None
            )
            if args.project_command == "add":
                result = service.add_project(
                    args.name,
                    args.description,
                    args.priority,
                    args.target_date,
                    tuple(args.goal_id),
                    tuple(args.task_id),
                    now=now,
                )
                print_json({"status": "ok", "project": result})
            elif args.project_command == "list":
                print_json(
                    {
                        "projects": service.list_projects(
                            include_archived=args.include_archived
                        )
                    }
                )
            elif args.project_command == "milestone-add":
                result = service.add_project_milestone(
                    args.project_id, args.title, args.target_date, now=now
                )
                print_json({"status": "ok", **result})
            elif args.project_command == "milestone-update":
                result = service.update_project_milestone(
                    args.project_id, args.milestone_id, args.status, now=now
                )
                print_json(
                    {
                        "status": "ok",
                        "project": {**result["project"], "summary": result["summary"]},
                        "milestone": result["milestone"],
                    }
                )
            elif args.project_command == "progress":
                result = service.update_project_progress(
                    args.project_id, args.percent, args.note, args.correction, now=now
                )
                print_json(
                    {
                        "status": "ok",
                        "project": {**result["project"], "summary": result["summary"]},
                    }
                )
            else:
                result = service.archive_project(args.project_id, now=now)
                print_json({"status": "ok", "project": result})
        except (TypeError, ValueError) as exc:
            _error_exit("invalid_project", str(exc), 2)
        return

    if args.command == "research":
        try:
            now = (
                datetime.fromisoformat(args.now) if getattr(args, "now", None) else None
            )
            command = args.research_command
            if command in {"synthesize", "ask", "run"} and args.llm:
                config = LLMConfig.from_env(model_tier=args.model_tier)
                llm = OpenAICompatibleLLM(config) if config.is_configured else None
                service = NexusService(store, llm=llm, memory_retriever=retriever)
            if command == "create":
                result = service.create_research(
                    args.title, args.objective, args.question, now=now
                )
                print_json({"status": "ok", "research": result})
            elif command == "list":
                print_json(
                    {
                        "research": service.list_research(
                            include_archived=args.include_archived
                        )
                    }
                )
            elif command == "show":
                print_json({"research": service.show_research(args.research_id)})
            elif command == "question-add":
                print_json(
                    {
                        "status": "ok",
                        **service.add_research_question(
                            args.research_id, args.question, now=now
                        ),
                    }
                )
            elif command == "source-add":
                print_json(
                    {
                        "status": "ok",
                        **service.add_research_source(
                            args.research_id,
                            args.type,
                            args.title,
                            args.locator,
                            args.note,
                            now=now,
                        ),
                    }
                )
            elif command == "note-add":
                print_json(
                    {
                        "status": "ok",
                        **service.add_research_note(
                            args.research_id,
                            args.text,
                            args.source_id,
                            args.tag,
                            now=now,
                        ),
                    }
                )
            elif command == "experiment-add":
                print_json(
                    {
                        "status": "ok",
                        **service.add_research_experiment(
                            args.research_id,
                            args.title,
                            args.hypothesis,
                            args.method,
                            args.result,
                            args.status,
                            args.source_id,
                            now=now,
                        ),
                    }
                )
            elif command == "investigate":
                literature_search = None
                if args.live_tools:
                    manager = build_tool_manager(load_tool_settings(), nexus_home())

                    def literature_search(query: str, limit: int) -> dict[str, Any]:
                        return manager.execute(
                            "literature", "read", query=query, limit=limit
                        ).data

                result = service.investigate_research(
                    args.research_id,
                    args.query,
                    literature_search=literature_search,
                    now=now,
                )
                print_json({"status": "ok", "investigation": result})
            elif command == "synthesize":
                result = service.synthesize_research(
                    args.research_id, use_llm=args.llm, now=now
                )
                print_json({"status": "ok", "synthesis": result})
            elif command == "ask":
                result = service.ask_research(
                    args.research_id,
                    args.question,
                    use_llm=args.llm,
                    now=now,
                )
                print_json({"status": "ok", "answer": result})
            elif command == "document-add":
                result = service.add_research_document(args.research_id, args.path)
                print_json({"status": "ok", **result})
            elif command == "document-list":
                result = service.list_research_documents(args.research_id)
                print_json({"documents": result})
            elif command == "document-show":
                result = service.show_research_document(
                    args.research_id, args.document_id
                )
                print_json({"document": result})
            elif command == "document-remove":
                result = service.remove_research_document(
                    args.research_id, args.document_id
                )
                print_json({"status": "ok", **result})
            elif command == "document-reindex":
                result = service.reindex_research_document(
                    args.research_id, args.document_id
                )
                print_json({"status": "ok", **result})
            elif command == "document-search":
                result = service.search_research_documents(
                    args.research_id, args.query, args.limit
                )
                print_json({"results": result})
            elif command == "web-add":
                result = service.add_research_web(args.research_id, args.url)
                print_json({"status": "ok", **result})
            elif command == "repo-index":
                result = service.index_research_repository(args.research_id, args.path)
                print_json({"status": "ok", "repository": result})
            elif command == "run":
                result = service.run_research_loop(
                    args.research_id,
                    args.question,
                    max_cycles=args.max_cycles,
                    use_llm=args.llm,
                    now=now,
                )
                print_json({"status": "ok", "run": result})
            elif command == "experiment-run":
                result = service.run_research_experiment(
                    args.research_id,
                    args.command,
                    args.cwd,
                    allowed_root=args.allowed_root,
                    allowed_executables=set(args.allow_executable),
                    approved=args.approve,
                    timeout_seconds=args.timeout,
                )
                print_json({"status": "ok", "experiment": result})
            else:
                result = service.archive_research(args.research_id, now=now)
                print_json({"status": "ok", "research": result})
        except (TypeError, ValueError) as exc:
            _error_exit("invalid_research", str(exc), 2)
        return

    if args.command == "suggestion":
        try:
            now = (
                datetime.fromisoformat(args.now) if getattr(args, "now", None) else None
            )
            profile, _runtime = load_runtime_settings()
            if args.suggestion_command in {"list", "refresh"}:
                if args.llm:
                    config = LLMConfig.from_env(model_tier=args.model_tier)
                    llm = OpenAICompatibleLLM(config) if config.is_configured else None
                    service = NexusService(store, llm=llm, memory_retriever=retriever)
                calendar = None
                calendar_requested = bool(
                    args.live_tools and args.suggestion_command == "refresh"
                )
                if calendar_requested:
                    try:
                        calendar_result = build_tool_manager(
                            load_tool_settings(), nexus_home()
                        ).execute(
                            "calendar",
                            "read",
                            days=1,
                            now=now.isoformat() if now else None,
                        )
                        raw_events = calendar_result.data.get("events")
                        calendar = raw_events if isinstance(raw_events, list) else None
                    except ToolError:
                        calendar = None
                suggestions = service.list_suggestions(
                    timezone=profile.timezone,
                    now=now,
                    refresh=args.suggestion_command == "refresh",
                    limit=args.limit,
                    use_llm=args.llm,
                    calendar=calendar,
                    calendar_requested=calendar_requested,
                )
                print_json(
                    {
                        "suggestions": suggestions,
                        "context": service.suggestion_context(),
                    }
                )
            elif args.suggestion_command == "accept":
                result = service.accept_suggestion(
                    args.suggestion_id,
                    approved=args.approve,
                    timezone=profile.timezone,
                    now=now,
                )
                print_json({"status": "ok", **result})
            else:
                result = service.dismiss_suggestion(
                    args.suggestion_id,
                    timezone=profile.timezone,
                    now=now,
                )
                print_json({"status": "ok", "suggestion": result})
        except (TypeError, ValueError) as exc:
            _error_exit("invalid_suggestion", str(exc), 2)
        return
    if args.command == "replan":
        try:
            now = datetime.fromisoformat(args.now) if args.now else None
            profile, _runtime = load_runtime_settings()
            events = None if args.calendar_unavailable else json.loads(args.events_json)
            if args.replan_command == "preview":
                preview = service.preview_replan(
                    args.date,
                    events,
                    (args.working_start, args.working_end),
                    timezone=profile.timezone,
                    now=now,
                )
                print_json({"preview": preview})
            else:
                preview = json.loads(args.preview_json)
                result = service.apply_replan(
                    preview, events, timezone=profile.timezone, now=now
                )
                print_json({"status": "ok", "result": result})
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            _error_exit("invalid_replan", str(exc), 2)
        return
    tool_settings = load_tool_settings()
    tool_manager = build_tool_manager(tool_settings, nexus_home())
    mcp_settings = load_mcp_settings()
    mcp_manager = build_mcp_manager(mcp_settings, nexus_home())
    agent_traces = AgentTraceStore(nexus_home() / "agent_runs.jsonl")

    if args.command == "agent":
        if args.agent_command == "runs":
            print_json({"runs": agent_traces.recent(args.limit)})
            return
        run = agent_traces.find(args.run_id)
        if run is None:
            print_json(
                {"status": "error", "error": f"Agent run '{args.run_id}' not found."}
            )
            raise SystemExit(1)
        print_json({"run": run})
        return

    if args.command == "memory":
        try:
            if args.memory_command == "add":
                memory = service.add_memory(
                    args.text,
                    args.tags,
                    importance=args.importance,
                    privacy=args.privacy,
                    expires_at=args.expires_at,
                    pinned=args.pin,
                )
                print_json(
                    {
                        "status": memory_mutation_status(memory.__dict__),
                        "memory": memory.__dict__,
                    }
                )
                return
            if args.memory_command == "list":
                print_json(
                    {
                        "memories": service.list_memories(
                            include_archived=args.include_archived,
                            include_forgotten=args.include_forgotten,
                        )
                    }
                )
                return
            if args.memory_command == "show":
                print_json({"memory": service.show_memory(args.memory_id)})
                return
            if args.memory_command == "search":
                print_json({"results": service.search_memories(args.query)})
                return
            if args.memory_command == "retrieve":
                now = datetime.fromisoformat(args.now) if args.now else None
                print_json(
                    service.retrieve_memories_result(
                        args.query,
                        args.limit,
                        privacy=args.privacy,
                        include_archived=args.include_archived,
                        task_context=args.task_context,
                        now=now,
                    )
                )
                return
            if args.memory_command == "update":
                values: dict[str, object] = {}
                if args.importance is not None:
                    values["importance"] = args.importance
                if args.privacy is not None:
                    values["privacy"] = args.privacy
                if args.expires_at is not None:
                    values["expires_at"] = (
                        None if args.expires_at.lower() == "none" else args.expires_at
                    )
                if args.pin:
                    values["pinned"] = True
                elif args.unpin:
                    values["pinned"] = False
                result = service.update_memory(args.memory_id, **values)
                print_json(
                    {
                        "status": memory_mutation_status(result),
                        "memory": result,
                    }
                )
                return
            if args.memory_command == "relate":
                relation = "supersedes" if args.supersedes else "conflicts_with"
                target_id = args.supersedes or args.conflicts_with
                result = service.relate_memory(args.memory_id, relation, target_id)
                print_json(
                    {
                        "status": memory_mutation_status(result),
                        "relation": result,
                    }
                )
                return
            if args.memory_command in {"archive", "restore", "forget"}:
                operation = getattr(service, f"{args.memory_command}_memory")
                result = operation(args.memory_id)
                print_json(
                    {
                        "status": memory_mutation_status(result),
                        "memory": result,
                    }
                )
                return
            if args.memory_command == "purge":
                result = service.purge_memory(args.memory_id, confirm=args.confirm)
                print_json(
                    {
                        "status": memory_mutation_status(result),
                        "result": result,
                    }
                )
                return
            if args.memory_command == "compress":
                now = datetime.fromisoformat(args.now) if args.now else None
                result = service.compress_memories(
                    older_than_days=args.older_than_days,
                    max_importance=args.max_importance,
                    dry_run=args.dry_run,
                    now=now,
                )
                print_json(
                    {
                        "status": memory_mutation_status(result),
                        "compression": result,
                    }
                )
                return
            if args.memory_command == "maintain":
                now = datetime.fromisoformat(args.now) if args.now else None
                result = service.maintain_memories(now=now, dry_run=args.dry_run)
                print_json(
                    {
                        "status": memory_mutation_status(result),
                        "maintenance": result,
                    }
                )
                return
            if args.memory_command == "reindex":
                report = service.reindex_memories()
                print_json(
                    {
                        "status": "error" if report.get("error") else "ok",
                        "index": report,
                    }
                )
                return
            if args.memory_command == "index-status":
                print_json({"index": service.rag_status()})
                return
        except (MemoryLifecycleError, ValueError) as exc:
            print_json({"status": "error", "error": str(exc)})
            raise SystemExit(2) from exc
    if args.command == "tool":
        if args.tool_command == "audit":
            print_json({"events": tool_manager.audit_events(args.limit)})
            return
        try:
            if args.tool_command == "weather":
                result = tool_manager.execute("weather", "read", location=args.location)
            elif args.tool_command == "calendar":
                result = tool_manager.execute(
                    "calendar", "read", days=args.days, now=args.now
                )
            elif args.tool_command == "todo":
                result = tool_manager.execute("todo", "read", limit=args.limit)
            elif args.tool_command == "github":
                result = tool_manager.execute(
                    "github", "read", repo=args.repo, limit=args.limit
                )
            elif args.tool_command == "notion":
                result = tool_manager.execute(
                    "notion", "read", query=args.query, limit=args.limit
                )
            elif args.tool_command == "literature":
                result = tool_manager.execute(
                    "literature", "read", query=args.query, limit=args.limit
                )
            elif args.tool_command == "email":
                result = tool_manager.execute(
                    "email", "read", limit=args.limit, unread_only=not args.all
                )
            else:
                result = tool_manager.execute(
                    "filesystem",
                    args.files_command,
                    path=args.path,
                    query=args.query,
                    max_bytes=args.max_bytes,
                )
            print_json({"status": "ok", "result": result.to_dict()})
        except ToolError as exc:
            print_json(
                {"status": "error", "tool": args.tool_command, "error": str(exc)}
            )
            raise SystemExit(1) from exc
        return

    if args.command == "mcp":
        if args.mcp_command == "servers":
            print_json({"servers": mcp_manager.servers()})
            return
        if args.mcp_command == "audit":
            print_json({"events": mcp_manager.audit_events(args.limit)})
            return
        arguments: dict[str, object] = {}
        if args.mcp_command == "call":
            try:
                arguments = parse_json_object(args.arguments)
            except ValueError as exc:
                print_json({"status": "error", "error": str(exc)})
                raise SystemExit(2) from exc
        try:
            if args.mcp_command == "tools":
                tools = mcp_manager.discover(args.server)
                print_json(
                    {"server": args.server, "tools": [tool.to_dict() for tool in tools]}
                )
            else:
                result = mcp_manager.call(
                    args.server, args.tool, arguments, approved=args.approve
                )
                print_json(
                    {"status": "ok", "server": args.server, "result": result.to_dict()}
                )
        except MCPError as exc:
            print_json({"status": "error", "error": str(exc)})
            raise SystemExit(1) from exc
        return
    if args.command == "goal":
        if args.goal_command == "add":
            goal = service.add_goal(args.title, args.description, args.cadence_days)
            print_json({"status": "ok", "goal": service._goal_to_dict(goal)})
            return
        if args.goal_command == "list":
            print_json({"goals": service.list_goals()})
            return
        if args.goal_command == "check-in":
            goal = service.check_in_goal(args.goal_id, args.note)
            print_json({"status": "ok", "goal": goal})
            return

    if args.command == "plan":
        now = datetime.fromisoformat(args.now) if args.now else None
        mcp_context = (
            mcp_manager.planning_context()
            if args.live_mcp and not args.agents
            else None
        )
        if args.llm:
            config = LLMConfig.from_env(model_tier=args.model_tier)
            llm = OpenAICompatibleLLM(config) if config.is_configured else None
            service = NexusService(store, llm=llm, memory_retriever=retriever)
        if args.agents:
            orchestrator = AgentOrchestrator(
                service, mcp_manager=mcp_manager, trace_store=agent_traces
            )
            print_json(
                orchestrator.run_plan(
                    user_name=args.name,
                    now=now,
                    coach_mode=args.coach_mode,
                    use_llm=args.llm,
                    mcp_context=mcp_context,
                )
            )
        else:
            print_json(
                service.daily_plan(
                    user_name=args.name,
                    now=now,
                    coach_mode=args.coach_mode,
                    use_llm=args.llm,
                    include_prompt=args.show_prompt,
                    mcp_context=mcp_context,
                )
            )
        return

    if args.command == "task":
        if args.task_command == "list":
            print_json({"tasks": service.list_daily_tasks(args.date)})
            return
        if args.task_command == "update":
            task = service.update_daily_task(
                args.task_id,
                status=args.status,
                blocker=args.blocker,
                unresolved=args.unresolved,
                note=args.note,
            )
            print_json({"status": "ok", "task": task})
            return

    if args.command == "review":
        now = datetime.fromisoformat(args.now) if args.now else None
        if args.review_command == "day":
            if args.llm:
                config = LLMConfig.from_env(model_tier=args.model_tier)
                llm = OpenAICompatibleLLM(config) if config.is_configured else None
                service = NexusService(store, llm=llm, memory_retriever=retriever)
            if args.agents:
                orchestrator = AgentOrchestrator(
                    service, mcp_manager=mcp_manager, trace_store=agent_traces
                )
                print_json(
                    orchestrator.run_review(
                        user_name=args.name,
                        now=now,
                        use_llm=args.llm,
                        coach_mode=args.coach_mode,
                    )
                )
            else:
                print_json(
                    service.daily_review(
                        user_name=args.name,
                        now=now,
                        use_llm=args.llm,
                        include_prompt=args.show_prompt,
                        coach_mode=args.coach_mode,
                    )
                )
            return
        print_json(service.proactive_review(now))
        return

    if args.command == "briefing":
        now = datetime.fromisoformat(args.now) if args.now else None
        print_json(
            _briefing_result(
                args,
                user_name=args.name,
                now=now,
                service=service,
                store=store,
                retriever=retriever,
                tool_manager=tool_manager,
                mcp_manager=mcp_manager,
                agent_traces=agent_traces,
            )
        )
        return

    if args.command == "config" and args.config_command == "llm":
        if args.llm_command == "set":
            settings, path = update_llm_settings(
                provider=args.provider,
                api_key=args.api_key,
                base_url=args.base_url,
                simple_model=args.simple_model,
                complex_model=args.complex_model,
                default_tier=args.default_tier,
                timeout_seconds=args.timeout_seconds,
            )
            print_json({"status": "ok", "path": str(path), "llm": settings.masked()})
            return
        if args.llm_command == "show":
            settings = load_llm_settings()
            print_json({"llm": settings.masked()})
            return

    if args.command == "config" and args.config_command == "embedding":
        if args.embedding_command == "set":
            settings, path = update_embedding_settings(
                provider=args.provider,
                model=args.model,
                api_key=args.api_key,
                base_url=args.base_url,
                qdrant_url=args.qdrant_url,
                qdrant_api_key=args.qdrant_api_key,
                collection_name=args.collection,
                timeout_seconds=args.timeout_seconds,
            )
            print_json(
                {"status": "ok", "path": str(path), "embedding": settings.masked()}
            )
            return
        if args.embedding_command == "show":
            print_json({"embedding": load_embedding_settings().masked()})
            return

    if args.command == "config" and args.config_command == "tool":
        if args.tool_config_command == "set":
            values_by_tool = {
                "weather": {"location": args.location},
                "calendar": {"calendar_url": args.calendar_url},
                "todo": {"token": args.token},
                "github": {"token": args.token, "repo": args.repo},
                "notion": {"token": args.token},
                "email": {
                    "host": args.host,
                    "port": args.port,
                    "username": args.username,
                    "password": args.password,
                    "mailbox": args.mailbox,
                    "timeout_seconds": args.timeout_seconds,
                },
                "filesystem": {"roots": args.roots},
                "literature": {"mailto": args.mailto},
            }
            try:
                settings, path = update_tool_settings(
                    args.tool_name, values_by_tool[args.tool_name]
                )
            except ValueError as exc:
                print_json(
                    {"status": "error", "tool": args.tool_name, "error": str(exc)}
                )
                raise SystemExit(2) from exc
            print_json(
                {
                    "status": "ok",
                    "path": str(path),
                    "tools": masked_tool_settings(settings),
                }
            )
            return
        if args.tool_config_command == "disable":
            settings, path = update_tool_settings(args.tool_name, enabled=False)
            print_json(
                {
                    "status": "ok",
                    "path": str(path),
                    "tools": masked_tool_settings(settings),
                }
            )
            return
        if args.tool_config_command == "show":
            print_json({"tools": masked_tool_settings(load_tool_settings())})
            return

    if args.command == "config" and args.config_command == "mcp":
        try:
            if args.mcp_config_command == "add":
                server = {
                    "enabled": True,
                    "transport": args.transport,
                    "timeout_seconds": args.timeout_seconds,
                    "max_retries": args.max_retries,
                    "tool_policies": {},
                    "planning_tools": [],
                }
                if args.transport == "stdio":
                    server.update(
                        {
                            "command": args.server_command,
                            "args": args.server_args,
                            "env": parse_pairs(args.env, "Environment"),
                        }
                    )
                else:
                    server.update(
                        {"url": args.url, "headers": parse_pairs(args.header, "Header")}
                    )
                settings, path = upsert_mcp_server(args.server_name, server)
            elif args.mcp_config_command == "disable":
                settings, path = disable_mcp_server(args.server_name)
            elif args.mcp_config_command == "remove":
                settings, path = remove_mcp_server(args.server_name)
            elif args.mcp_config_command == "policy":
                settings, path = set_mcp_tool_policy(
                    args.server_name, args.tool, args.policy
                )
            elif args.mcp_config_command == "planning-tool":
                arguments = parse_json_object(args.arguments)
                settings, path = set_mcp_planning_tool(
                    args.server_name, args.tool, arguments
                )
            else:
                print_json({"servers": masked_mcp_settings(load_mcp_settings())})
                return
        except ValueError as exc:
            print_json({"status": "error", "error": str(exc)})
            raise SystemExit(2) from exc
        print_json(
            {
                "status": "ok",
                "path": str(path),
                "servers": masked_mcp_settings(settings),
            }
        )
        return
    parser.error("Unknown command")


if __name__ == "__main__":
    main()
