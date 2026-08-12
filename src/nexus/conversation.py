from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Intent:
    name: str
    arguments: dict[str, Any]
    confidence: float
    source: str
    requires_approval: bool


INTENT_SCHEMAS: dict[str, dict[str, type]] = {
    "show_today": {},
    "list_goals": {},
    "list_habits": {},
    "list_projects": {},
    "list_suggestions": {},
    "list_research": {},
    "show_research": {"research_id": str},
    "list_research_documents": {"research_id": str},
    "search_research_documents": {"research_id": str, "query": str},
    "add_memory": {"text": str},
    "add_goal": {"title": str},
    "add_habit": {"name": str},
    "add_project": {"name": str},
    "check_in_habit": {"habit_id": str},
    "complete_task": {"task_id": str},
    "update_project_progress": {"project_id": str, "percent": int},
    "plan_day": {},
    "preview_replan": {},
    "briefing": {},
    "review_day": {},
}

APPROVAL_INTENTS = {
    "add_memory",
    "add_goal",
    "add_habit",
    "add_project",
    "complete_task",
    "update_project_progress",
    "plan_day",
}


class IntentRegistry:
    def parse_local(self, text: str) -> Intent | None:
        raw = str(text).strip()
        normalized = raw.casefold()
        fixed = (
            (
                ("show my goals", "show goals", "list goals", "查看目标", "列出目标"),
                "list_goals",
            ),
            (
                (
                    "show my habits",
                    "show habits",
                    "list habits",
                    "查看我的习惯",
                    "查看习惯",
                    "列出习惯",
                ),
                "list_habits",
            ),
            (
                (
                    "show my projects",
                    "show projects",
                    "list projects",
                    "查看项目",
                    "列出项目",
                ),
                "list_projects",
            ),
            (
                ("show suggestions", "list suggestions", "查看建议", "列出建议"),
                "list_suggestions",
            ),
            (
                (
                    "list research",
                    "show research projects",
                    "查看研究项目",
                    "列出研究项目",
                ),
                "list_research",
            ),
            (
                (
                    "show today",
                    "today",
                    "today's plan",
                    "今天安排",
                    "今日任务",
                    "查看今天",
                ),
                "show_today",
            ),
            (("plan my day", "plan today", "安排今天", "制定今日计划"), "plan_day"),
            (
                ("preview replan", "replan today", "重新安排今天", "预览重排"),
                "preview_replan",
            ),
            (("morning briefing", "briefing", "早晨简报", "今日简报"), "briefing"),
            (("review today", "daily review", "复盘今天", "今日复盘"), "review_day"),
        )
        for phrases, name in fixed:
            if normalized in phrases:
                return self._intent(name, {})

        patterns: list[tuple[str, str, Any]] = [
            (
                r"^(?:list research documents|列出研究文档)\s+([\w-]+)$",
                "list_research_documents",
                lambda m: {"research_id": m.group(1)},
            ),
            (
                r"^(?:search research|搜索研究)\s+([\w-]+)\s+(.+)$",
                "search_research_documents",
                lambda m: {"research_id": m.group(1), "query": m.group(2).strip()},
            ),
            (
                r"^(?:remember(?: that)?|记住(?:我)?)[：:]?\s*(.+)$",
                "add_memory",
                lambda m: {"text": m.group(1).strip()},
            ),
            (
                r"^(?:add goal|添加目标)[：:]?\s*(.+)$",
                "add_goal",
                lambda m: {"title": m.group(1).strip()},
            ),
            (
                r"^(?:add habit|添加习惯)[：:]?\s*(.+)$",
                "add_habit",
                lambda m: {"name": m.group(1).strip()},
            ),
            (
                r"^(?:add project|添加项目)[：:]?\s*(.+)$",
                "add_project",
                lambda m: {"name": m.group(1).strip()},
            ),
            (
                r"^(?:check in habit|habit check-in|习惯打卡)\s+([\w-]+)$",
                "check_in_habit",
                lambda m: {"habit_id": m.group(1)},
            ),
            (
                r"^(?:complete task|完成任务)\s+([\w-]+)$",
                "complete_task",
                lambda m: {"task_id": m.group(1)},
            ),
            (
                r"^(?:project|项目)\s+([\w-]+)\s+(?:progress|进度)\s+(\d{1,3})%?$",
                "update_project_progress",
                lambda m: {"project_id": m.group(1), "percent": int(m.group(2))},
            ),
            (
                r"^(?:show research|查看研究)\s+([\w-]+)$",
                "show_research",
                lambda m: {"research_id": m.group(1)},
            ),
        ]
        for pattern, name, arguments in patterns:
            match = re.match(pattern, raw, flags=re.IGNORECASE)
            if match:
                values = arguments(match)
                if all(values.values()):
                    return self._intent(name, values)
        return None

    def parse_llm(self, text: str, llm: Any) -> Intent:
        catalog = {
            name: {key: value.__name__ for key, value in schema.items()}
            for name, schema in INTENT_SCHEMAS.items()
        }
        response = llm.generate(
            "Select one allowed intent. Return only strict JSON with exactly intent, arguments, and confidence. Never return commands, URLs, tools, or extra fields.",
            json.dumps({"text": text[:2_000], "catalog": catalog}, ensure_ascii=False),
        )
        try:
            payload = json.loads(response)
        except json.JSONDecodeError as exc:
            raise ValueError("LLM intent must be valid JSON.") from exc
        if not isinstance(payload, dict) or set(payload) != {
            "intent",
            "arguments",
            "confidence",
        }:
            raise ValueError("LLM intent used an invalid envelope.")
        name = payload["intent"]
        arguments = payload["arguments"]
        confidence = payload["confidence"]
        if name not in INTENT_SCHEMAS or not isinstance(arguments, dict):
            raise ValueError("LLM intent is not allowed.")
        if (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0 <= confidence <= 1
        ):
            raise ValueError("LLM intent confidence is invalid.")
        self._validate_arguments(name, arguments)
        return Intent(
            name, arguments, float(confidence), "llm", name in APPROVAL_INTENTS
        )

    @staticmethod
    def _validate_arguments(name: str, arguments: dict[str, Any]) -> None:
        schema = INTENT_SCHEMAS[name]
        if set(arguments) != set(schema):
            raise ValueError("Intent arguments do not match the registered schema.")
        for key, expected in schema.items():
            value = arguments[key]
            if not isinstance(value, expected) or (
                expected is int and isinstance(value, bool)
            ):
                raise ValueError(f"Intent argument '{key}' has the wrong type.")
            if isinstance(value, str) and (not value.strip() or len(value) > 2_000):
                raise ValueError(f"Intent argument '{key}' is empty or too long.")
        if name == "update_project_progress" and not 0 <= arguments["percent"] <= 100:
            raise ValueError("Project progress must be from 0 to 100.")

    @staticmethod
    def _intent(name: str, arguments: dict[str, Any]) -> Intent:
        return Intent(name, arguments, 0.98, "local", name in APPROVAL_INTENTS)


class ConversationService:
    def __init__(self, nexus: Any, *, timezone: str = "UTC", llm: Any = None) -> None:
        self.nexus = nexus
        self.timezone = timezone
        self.llm = llm
        self.registry = IntentRegistry()

    def handle(
        self,
        text: str,
        *,
        approved: bool = False,
        use_llm: bool = False,
        show_intent: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = now or datetime.now(UTC)
        intent = self.registry.parse_local(text)
        degradations: list[str] = []
        if intent is None and use_llm:
            if self.llm is None:
                degradations.append("llm_unavailable")
            else:
                try:
                    intent = self.registry.parse_llm(text, self.llm)
                except (ValueError, RuntimeError):
                    degradations.append("llm_intent_rejected")
        if intent is None:
            envelope = self._envelope(None, degradations)
            envelope["explanation"] = (
                "I could not map that request to an allowed Nexus action."
            )
            return envelope
        envelope = self._envelope(intent, degradations)
        if show_intent:
            envelope["intent_details"] = asdict(intent)
        if intent.requires_approval and not approved:
            envelope["preview"] = {
                "intent": intent.name,
                "arguments": deepcopy_arguments(intent.arguments),
            }
            envelope["explanation"] = (
                "Review this local change and approve it before Nexus applies it."
            )
            return envelope
        envelope["result"] = self._dispatch(intent, current)
        envelope["explanation"] = (
            "Completed through the registered local Nexus service."
        )
        return envelope

    @staticmethod
    def _envelope(intent: Intent | None, degradations: list[str]) -> dict[str, Any]:
        return {
            "intent": intent.name if intent else "unknown",
            "confidence": intent.confidence if intent else 0.0,
            "source": intent.source if intent else "none",
            "requires_approval": intent.requires_approval if intent else False,
            "preview": None,
            "result": None,
            "explanation": "",
            "degradations": degradations,
        }

    def _dispatch(self, intent: Intent, now: datetime) -> Any:
        args = intent.arguments
        local_date = now.astimezone(ZoneInfo(self.timezone)).date().isoformat()
        if intent.name == "show_today":
            return {"tasks": self.nexus.list_daily_tasks(local_date)}
        if intent.name == "list_goals":
            return {"goals": self.nexus.list_goals()}
        if intent.name == "list_habits":
            return {"habits": self.nexus.list_habits(timezone=self.timezone, now=now)}
        if intent.name == "list_projects":
            return {"projects": self.nexus.list_projects()}
        if intent.name == "list_suggestions":
            return {
                "suggestions": self.nexus.list_suggestions(
                    timezone=self.timezone, now=now
                )
            }
        if intent.name == "list_research":
            return {"research": self.nexus.list_research()}
        if intent.name == "show_research":
            return {"research": self.nexus.show_research(args["research_id"])}
        if intent.name == "list_research_documents":
            return {
                "documents": self.nexus.list_research_documents(args["research_id"])
            }
        if intent.name == "search_research_documents":
            return {
                "results": self.nexus.search_research_documents(
                    args["research_id"], args["query"]
                )
            }
        if intent.name == "add_memory":
            memory = self.nexus.add_memory(args["text"], [], now=now)
            return {"memory": memory.__dict__}
        if intent.name == "add_goal":
            return {"goal": self.nexus.add_goal(args["title"], "", 3).__dict__}
        if intent.name == "add_habit":
            habit = self.nexus.add_habit(
                args["name"], "", "daily", (), 1, None, timezone=self.timezone, now=now
            )
            return {"habit": habit}
        if intent.name == "add_project":
            return {
                "project": self.nexus.add_project(
                    args["name"], "", 3, None, (), (), now=now
                )
            }
        if intent.name == "check_in_habit":
            return self.nexus.check_in_habit(
                args["habit_id"],
                local_date,
                1,
                "Conversation check-in",
                timezone=self.timezone,
                now=now,
            )
        if intent.name == "complete_task":
            return {
                "task": self.nexus.update_daily_task(
                    args["task_id"], status="completed", now=now
                )
            }
        if intent.name == "update_project_progress":
            return self.nexus.update_project_progress(
                args["project_id"],
                args["percent"],
                "Conversation update",
                False,
                now=now,
            )
        if intent.name == "plan_day":
            return self.nexus.daily_plan(now=now)
        if intent.name == "preview_replan":
            return self.nexus.preview_replan(
                local_date, [], ("09:00", "18:00"), timezone=self.timezone, now=now
            )
        if intent.name == "briefing":
            return self.nexus.daily_briefing(now=now)
        if intent.name == "review_day":
            return self.nexus.daily_review(now=now)
        raise ValueError(f"Intent '{intent.name}' has no registered dispatcher.")


def deepcopy_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(arguments, ensure_ascii=False))
