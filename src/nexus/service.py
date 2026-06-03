from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from .store import JsonStore


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


#把 datetime 对象转成标准字符串。
def isoformat(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat()


@dataclass
class Memory:
    id: str
    text: str
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: isoformat(utc_now()))


@dataclass
class CheckIn:
    at: str
    note: str


@dataclass
class Goal:
    id: str
    title: str
    description: str
    cadence_days: int = 3
    status: str = "active"
    created_at: str = field(default_factory=lambda: isoformat(utc_now()))
    last_check_in: str | None = None
    check_ins: list[CheckIn] = field(default_factory=list)


class NexusService:
    def __init__(self, store: JsonStore):
        self.store = store

    def add_memory(self, text: str, tags: list[str]) -> Memory:
        state = self.store.load()
        memory = Memory(id=str(uuid4())[:8], text=text.strip(), tags=tags)
        state["memories"].append(asdict(memory))
        self.store.save(state)
        return memory

    def list_memories(self) -> list[dict[str, Any]]:
        state = self.store.load()
        return sorted(state["memories"], key=lambda item: item["created_at"], reverse=True)

    def search_memories(self, query: str) -> list[dict[str, Any]]:
        terms = {part.lower() for part in query.split() if part.strip()}
        results = []
        for memory in self.list_memories():
            haystack = f"{memory['text']} {' '.join(memory.get('tags', []))}".lower()
            score = sum(1 for term in terms if term in haystack)
            if score > 0:
                results.append((score, memory))
        results.sort(key=lambda item: (-item[0], item[1]["created_at"]), reverse=False)
        return [memory for _, memory in results]

    def add_goal(self, title: str, description: str, cadence_days: int) -> Goal:
        state = self.store.load()
        goal = Goal(
            id=str(uuid4())[:8],
            title=title.strip(),
            description=description.strip(),
            cadence_days=cadence_days,
        )
        state["goals"].append(self._goal_to_dict(goal))
        self.store.save(state)
        return goal

    def list_goals(self) -> list[dict[str, Any]]:
        state = self.store.load()
        return sorted(state["goals"], key=lambda item: item["created_at"])

    def check_in_goal(self, goal_id: str, note: str) -> dict[str, Any]:
        state = self.store.load()
        for goal in state["goals"]:
            if goal["id"] != goal_id:
                continue
            timestamp = isoformat(utc_now())
            goal["last_check_in"] = timestamp
            goal.setdefault("check_ins", []).append({"at": timestamp, "note": note.strip()})
            self.store.save(state)
            return goal
        raise ValueError(f"Goal '{goal_id}' not found.")

    def proactive_review(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or utc_now()
        state = self.store.load()
        reminders: list[str] = []

        for goal in state["goals"]:
            if goal.get("status") != "active":
                continue

            reference_time = parse_timestamp(goal.get("last_check_in")) or parse_timestamp(goal["created_at"])
            if reference_time is None:
                continue

            if now - reference_time >= timedelta(days=int(goal.get("cadence_days", 3))):
                days_since = (now - reference_time).days
                reminders.append(
                    f"[goal:{goal['id']}]「{goal['title']}」已经 {days_since} 天没有更新了，"
                    "建议今天做一次打卡，并明确下一步行动。"
                )

        latest_memory = None
        memories = state.get("memories", [])
        if memories:
            latest_memory = max(memories, key=lambda item: item["created_at"])

        if latest_memory:
            latest_memory_at = parse_timestamp(latest_memory["created_at"])
            if latest_memory_at and now - latest_memory_at >= timedelta(days=7):
                reminders.append(
                    "你已经 7 天以上没有添加新的记忆了，建议补充一次最近的生活或学习状态。"
                )

        return {
            "generated_at": isoformat(now),
            "reminders": reminders,
        }

    def daily_briefing(
        self,
        user_name: str = "Louis",
        weather: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or utc_now()
        state = self.store.load()
        active_goals = [
            goal for goal in state.get("goals", [])
            if goal.get("status") == "active"
        ]
        active_goals.sort(
            key=lambda goal: (
                parse_timestamp(goal.get("last_check_in"))
                or parse_timestamp(goal.get("created_at"))
                or now
            )
        )

        important_goals = active_goals[:3]
        reminders = self.proactive_review(now)["reminders"]
        latest_memory = self._latest_memory(state)
        weather_text = weather or "天气信息暂未接入"
        date_text = f"{now.month}月{now.day}日"

        if important_goals:
            suggested_goal = important_goals[0]
            suggestion = (
                f"我建议你今天先推进「{suggested_goal['title']}」，"
                "先做一个 30 分钟的小任务。"
            )
        elif latest_memory:
            suggestion = f"你最近记录过：{latest_memory['text']}。今天可以围绕它安排一个小行动。"
        else:
            suggestion = "今天可以先添加一个长期目标，让我开始帮你追踪。"

        lines = [
            f"早上好，{user_name}。",
            "",
            f"今天是 {date_text}，{weather_text}。",
            "",
        ]

        if important_goals:
            lines.append(f"你今天有 {len(important_goals)} 件重要的事：")
            lines.append("")
            for index, goal in enumerate(important_goals, start=1):
                description = goal.get("description")
                if description:
                    lines.append(f"{index}. {goal['title']} - {description}")
                else:
                    lines.append(f"{index}. {goal['title']}")
        else:
            lines.append("你今天还没有设置重要目标。")

        lines.extend(["", suggestion])

        if reminders:
            lines.append("")
            lines.append("另外，我注意到：")
            lines.extend(f"- {reminder}" for reminder in reminders)

        lines.extend(["", "今天不用做完所有事，先把最重要的一步往前推。"])

        return {
            "generated_at": isoformat(now),
            "user_name": user_name,
            "today": {
                "date": date_text,
                "weather": weather_text,
            },
            "important_goals": important_goals,
            "reminders": reminders,
            "suggestion": suggestion,
            "briefing": "\n".join(lines),
        }

    @staticmethod
    def _latest_memory(state: dict[str, Any]) -> dict[str, Any] | None:
        memories = state.get("memories", [])
        if not memories:
            return None
        return max(memories, key=lambda item: item["created_at"])

    @staticmethod
    def _goal_to_dict(goal: Goal) -> dict[str, Any]:
        data = asdict(goal)
        data["check_ins"] = [asdict(check_in) for check_in in goal.check_ins]
        return data
