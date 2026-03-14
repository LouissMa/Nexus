from __future__ import annotations

import argparse
import json
from datetime import datetime

from .service import NexusService
from .store import JsonStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nexus",
        description="NEXUS Phase 1 CLI MVP: memory, goals, and proactive review.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    memory_parser = subparsers.add_parser("memory", help="Manage long-term memories.")
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command", required=True)

    memory_add = memory_subparsers.add_parser("add", help="Store a memory.")
    memory_add.add_argument("text", help="Memory text to store.")
    memory_add.add_argument("--tags", nargs="*", default=[], help="Optional tags.")

    memory_subparsers.add_parser("list", help="List memories.")

    memory_search = memory_subparsers.add_parser("search", help="Search memories.")
    memory_search.add_argument("query", help="Keyword query.")

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

    parser.error("Unknown command")


if __name__ == "__main__":
    main()
