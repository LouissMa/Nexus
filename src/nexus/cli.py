from __future__ import annotations

import argparse
import json
from datetime import datetime

from .config import load_llm_settings, update_llm_settings
from .llm import LLMConfig, OpenAICompatibleLLM
from .service import NexusService
from .store import JsonStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nexus",
        description="NEXUS Phase 1 CLI MVP: memory, goals, proactive review, and LLM briefing.",
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

    review_parser = subparsers.add_parser("review", help="Run proactive reminder review.")
    review_parser.add_argument(
        "--now",
        help="Optional ISO timestamp for deterministic review runs.",
    )

    briefing_parser = subparsers.add_parser("briefing", help="Generate a morning life briefing.")
    briefing_parser.add_argument("--name", default="Louis", help="User name for the greeting.")
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

    return parser


def print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    service = NexusService(JsonStore.from_env())

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
            print_json({"query": args.query, "results": service.retrieve_memories(args.query, args.limit)})
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

    if args.command == "review":
        now = datetime.fromisoformat(args.now) if args.now else None
        print_json(service.proactive_review(now))
        return

    if args.command == "briefing":
        now = datetime.fromisoformat(args.now) if args.now else None
        if args.llm:
            config = LLMConfig.from_env(model_tier=args.model_tier)
            llm = OpenAICompatibleLLM(config) if config.is_configured else None
            service = NexusService(JsonStore.from_env(), llm=llm)
        print_json(service.daily_briefing(args.name, args.weather, now, args.llm, args.show_prompt))
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

    parser.error("Unknown command")


if __name__ == "__main__":
    main()

