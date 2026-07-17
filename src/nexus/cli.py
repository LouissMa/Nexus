from __future__ import annotations

import argparse
import json
from datetime import datetime

from .config import (
    load_embedding_settings,
    load_llm_settings,
    load_tool_settings,
    masked_tool_settings,
    nexus_home,
    update_embedding_settings,
    update_llm_settings,
    update_tool_settings,
)
from .integrations.core import ToolError
from .integrations.manager import build_tool_manager
from .llm import LLMConfig, OpenAICompatibleLLM
from .planning import COACH_MODES, TASK_STATUSES
from .rag import build_memory_retriever
from .service import NexusService
from .store import JsonStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nexus",
        description="Nexus personal AI: memory, planning, reflection, hybrid RAG, and permissioned tools.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    memory_parser = subparsers.add_parser("memory", help="Manage long-term memories.")
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command", required=True)

    memory_add = memory_subparsers.add_parser("add", help="Store a memory.")
    memory_add.add_argument("text", help="Memory text to store.")
    memory_add.add_argument("--tags", nargs="*", default=[], help="Optional tags.")

    memory_subparsers.add_parser("list", help="List memories.")

    memory_search = memory_subparsers.add_parser("search", help="Search memories by keyword.")
    memory_search.add_argument("query", help="Keyword query.")

    memory_retrieve = memory_subparsers.add_parser("retrieve", help="Retrieve relevant memories with local RAG.")
    memory_retrieve.add_argument("query", help="Semantic retrieval query.")
    memory_retrieve.add_argument("--limit", type=int, default=5, help="Maximum number of memories to return.")

    memory_subparsers.add_parser("reindex", help="Rebuild the semantic memory index.")
    memory_subparsers.add_parser("index-status", help="Show semantic memory index status.")

    goal_parser = subparsers.add_parser("goal", help="Manage tracked goals.")
    goal_subparsers = goal_parser.add_subparsers(dest="goal_command", required=True)

    goal_add = goal_subparsers.add_parser("add", help="Create a goal.")
    goal_add.add_argument("title", help="Goal title.")
    goal_add.add_argument("--description", default="", help="Goal description.")
    goal_add.add_argument("--cadence-days", type=int, default=3, help="Check-in cadence in days.")

    goal_subparsers.add_parser("list", help="List goals.")

    goal_check_in = goal_subparsers.add_parser("check-in", help="Record progress on a goal.")
    goal_check_in.add_argument("goal_id", help="Goal identifier.")
    goal_check_in.add_argument("note", help="Short progress note.")

    plan_parser = subparsers.add_parser("plan", help="Create and inspect daily plans.")
    plan_parser.add_argument("plan_command", choices=["day"], help="Create today's structured plan.")
    plan_parser.add_argument("--name", default="User")
    plan_parser.add_argument("--coach-mode", choices=COACH_MODES, default="gentle")
    plan_parser.add_argument("--llm", action="store_true")
    plan_parser.add_argument("--model-tier", choices=["simple", "complex"])
    plan_parser.add_argument("--show-prompt", action="store_true")
    plan_parser.add_argument("--now", help="Optional ISO timestamp for deterministic planning.")

    task_parser = subparsers.add_parser("task", help="Inspect or update planned daily tasks.")
    task_subparsers = task_parser.add_subparsers(dest="task_command", required=True)
    task_list = task_subparsers.add_parser("list", help="List planned tasks.")
    task_list.add_argument("--date", help="Filter by YYYY-MM-DD plan date.")
    task_update = task_subparsers.add_parser("update", help="Update task progress and reflection fields.")
    task_update.add_argument("task_id")
    task_update.add_argument("--status", choices=TASK_STATUSES)
    task_update.add_argument("--blocker", help="Structured reason the task is blocked; empty text clears it.")
    task_update.add_argument("--unresolved", action="append", default=[], help="Open item to carry into review; repeat as needed.")
    task_update.add_argument("--note", help="Append a progress note.")

    review_parser = subparsers.add_parser("review", help="Run proactive reminders or daily reflection.")
    review_parser.add_argument("review_command", nargs="?", choices=["day"], help="Use `day` for evening daily review.")
    review_parser.add_argument("--name", default="User", help="User name for daily review.")
    review_parser.add_argument("--coach-mode", choices=COACH_MODES, default="gentle")
    review_parser.add_argument("--llm", action="store_true", help="Use configured LLM for daily review.")
    review_parser.add_argument(
        "--model-tier",
        choices=["simple", "complex"],
        help="Model tier to use for LLM review generation. Defaults to configured tier.",
    )
    review_parser.add_argument("--show-prompt", action="store_true", help="Include the generated LLM prompt in JSON output.")
    review_parser.add_argument(
        "--now",
        help="Optional ISO timestamp for deterministic review runs.",
    )

    briefing_parser = subparsers.add_parser("briefing", help="Generate a morning life briefing.")
    briefing_parser.add_argument("--name", default="User", help="User name for the greeting.")
    briefing_parser.add_argument("--weather", help="Optional weather summary.")
    briefing_parser.add_argument("--llm", action="store_true", help="Use configured LLM for the briefing.")
    briefing_parser.add_argument(
        "--model-tier",
        choices=["simple", "complex"],
        help="Model tier to use for LLM generation. Defaults to configured tier.",
    )
    briefing_parser.add_argument("--show-prompt", action="store_true", help="Include the generated LLM prompt in JSON output.")
    briefing_parser.add_argument(
        "--now",
        help="Optional ISO timestamp for deterministic briefing runs.",
    )
    briefing_parser.add_argument(
        "--live-tools",
        action="store_true",
        help="Fetch configured weather, calendar, and Todoist context.",
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
    email_tool = tool_subparsers.add_parser("email")
    email_tool.add_argument("--limit", type=int, default=10)
    email_tool.add_argument("--all", action="store_true", help="Include already-read messages.")
    files_tool = tool_subparsers.add_parser("files")
    files_tool.add_argument("files_command", choices=["list", "read", "search"])
    files_tool.add_argument("path")
    files_tool.add_argument("--query")
    files_tool.add_argument("--max-bytes", type=int, default=65536)
    audit_tool = tool_subparsers.add_parser("audit")
    audit_tool.add_argument("--limit", type=int, default=50)

    config_parser = subparsers.add_parser("config", help="Manage local Nexus configuration.")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    llm_parser = config_subparsers.add_parser("llm", help="Manage local LLM configuration.")
    llm_subparsers = llm_parser.add_subparsers(dest="llm_command", required=True)

    llm_set = llm_subparsers.add_parser("set", help="Save local LLM provider/model configuration.")
    llm_set.add_argument("--provider", choices=["openai", "deepseek", "custom"], required=True)
    llm_set.add_argument("--api-key", required=True, help="API key saved only to local ignored config.")
    llm_set.add_argument("--base-url", help="OpenAI-compatible base URL. Uses provider preset by default.")
    llm_set.add_argument("--simple-model", help="Cheap/fast model for simple tasks.")
    llm_set.add_argument("--complex-model", help="Stronger model for complex tasks.")
    llm_set.add_argument("--default-tier", choices=["simple", "complex"], default="simple")
    llm_set.add_argument("--timeout-seconds", type=int, default=30)

    llm_subparsers.add_parser("show", help="Show local LLM configuration with masked API key.")

    embedding_parser = config_subparsers.add_parser("embedding", help="Manage semantic RAG configuration.")
    embedding_subparsers = embedding_parser.add_subparsers(dest="embedding_command", required=True)

    embedding_set = embedding_subparsers.add_parser("set", help="Save embedding and Qdrant configuration.")
    embedding_set.add_argument("--provider", choices=["local_sparse", "fastembed", "openai", "custom"], required=True)
    embedding_set.add_argument("--model")
    embedding_set.add_argument("--api-key", help="Required for hosted embedding providers.")
    embedding_set.add_argument("--base-url", help="OpenAI-compatible API base URL.")
    embedding_set.add_argument("--qdrant-url", help="Remote Qdrant URL; local persistence is used when omitted.")
    embedding_set.add_argument("--qdrant-api-key")
    embedding_set.add_argument("--collection", default="nexus_memories")
    embedding_set.add_argument("--timeout-seconds", type=int, default=30)
    embedding_subparsers.add_parser("show", help="Show semantic RAG configuration with masked secrets.")

    tool_config_parser = config_subparsers.add_parser("tool", help="Manage external tool configuration.")
    tool_config_subparsers = tool_config_parser.add_subparsers(dest="tool_config_command", required=True)
    tool_set = tool_config_subparsers.add_parser("set", help="Configure and enable one tool.")
    tool_set.add_argument("tool_name", choices=["weather", "calendar", "todo", "github", "notion", "email", "filesystem"])
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
    tool_disable = tool_config_subparsers.add_parser("disable", help="Disable a configured tool.")
    tool_disable.add_argument("tool_name", choices=["weather", "calendar", "todo", "github", "notion", "email", "filesystem"])
    tool_config_subparsers.add_parser("show", help="Show tool configuration with masked secrets.")

    return parser


def print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    store = JsonStore.from_env()
    embedding_settings = load_embedding_settings()
    retriever = build_memory_retriever(embedding_settings, nexus_home())
    service = NexusService(store, memory_retriever=retriever)
    tool_settings = load_tool_settings()
    tool_manager = build_tool_manager(tool_settings, nexus_home())

    if args.command == "memory":
        if args.memory_command == "add":
            memory = service.add_memory(args.text, args.tags)
            print_json({"status": "ok", "memory": memory.__dict__})
            return
        if args.memory_command == "list":
            print_json({"memories": service.list_memories()})
            return
        if args.memory_command == "search":
            print_json({"results": service.search_memories(args.query)})
            return
        if args.memory_command == "retrieve":
            print_json(service.retrieve_memories_result(args.query, args.limit))
            return
        if args.memory_command == "reindex":
            report = service.reindex_memories()
            print_json({"status": "error" if report.get("error") else "ok", "index": report})
            return
        if args.memory_command == "index-status":
            print_json({"index": service.rag_status()})
            return

    if args.command == "tool":
        if args.tool_command == "audit":
            print_json({"events": tool_manager.audit_events(args.limit)})
            return
        try:
            if args.tool_command == "weather":
                result = tool_manager.execute("weather", "read", location=args.location)
            elif args.tool_command == "calendar":
                result = tool_manager.execute("calendar", "read", days=args.days, now=args.now)
            elif args.tool_command == "todo":
                result = tool_manager.execute("todo", "read", limit=args.limit)
            elif args.tool_command == "github":
                result = tool_manager.execute("github", "read", repo=args.repo, limit=args.limit)
            elif args.tool_command == "notion":
                result = tool_manager.execute("notion", "read", query=args.query, limit=args.limit)
            elif args.tool_command == "email":
                result = tool_manager.execute("email", "read", limit=args.limit, unread_only=not args.all)
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
            print_json({"status": "error", "tool": args.tool_command, "error": str(exc)})
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
        if args.llm:
            config = LLMConfig.from_env(model_tier=args.model_tier)
            llm = OpenAICompatibleLLM(config) if config.is_configured else None
            service = NexusService(store, llm=llm, memory_retriever=retriever)
        print_json(service.daily_plan(
            user_name=args.name, now=now, coach_mode=args.coach_mode,
            use_llm=args.llm, include_prompt=args.show_prompt,
        ))
        return

    if args.command == "task":
        if args.task_command == "list":
            print_json({"tasks": service.list_daily_tasks(args.date)})
            return
        if args.task_command == "update":
            task = service.update_daily_task(
                args.task_id, status=args.status, blocker=args.blocker,
                unresolved=args.unresolved, note=args.note,
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
            print_json(service.daily_review(user_name=args.name, now=now, use_llm=args.llm, include_prompt=args.show_prompt, coach_mode=args.coach_mode))
            return
        print_json(service.proactive_review(now))
        return

    if args.command == "briefing":
        now = datetime.fromisoformat(args.now) if args.now else None
        live_context = tool_manager.briefing_context(now) if args.live_tools else None
        if args.llm:
            config = LLMConfig.from_env(model_tier=args.model_tier)
            llm = OpenAICompatibleLLM(config) if config.is_configured else None
            service = NexusService(store, llm=llm, memory_retriever=retriever)
        print_json(service.daily_briefing(
            args.name, args.weather, now, args.llm, args.show_prompt,
            external_context=live_context,
        ))
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
            print_json({"status": "ok", "path": str(path), "embedding": settings.masked()})
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
            }
            try:
                settings, path = update_tool_settings(args.tool_name, values_by_tool[args.tool_name])
            except ValueError as exc:
                print_json({"status": "error", "tool": args.tool_name, "error": str(exc)})
                raise SystemExit(2) from exc
            print_json({
                "status": "ok",
                "path": str(path),
                "tools": masked_tool_settings(settings),
            })
            return
        if args.tool_config_command == "disable":
            settings, path = update_tool_settings(args.tool_name, enabled=False)
            print_json({
                "status": "ok",
                "path": str(path),
                "tools": masked_tool_settings(settings),
            })
            return
        if args.tool_config_command == "show":
            print_json({"tools": masked_tool_settings(load_tool_settings())})
            return

    parser.error("Unknown command")


if __name__ == "__main__":
    main()
