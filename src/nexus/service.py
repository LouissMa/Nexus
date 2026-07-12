from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from .llm import LLMError
from .rag import MemoryRetriever
from .store import JsonStore


class BriefingLLM(Protocol):
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        ...


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


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
    def __init__(
        self,
        store: JsonStore,
        llm: BriefingLLM | None = None,
        memory_retriever: MemoryRetriever | None = None,
    ):
        self.store = store
        self.llm = llm
        self.memory_retriever = memory_retriever or MemoryRetriever()

    def add_memory(self, text: str, tags: list[str]) -> Memory:
        state = self.store.load()
        memory = Memory(id=str(uuid4())[:8], text=text.strip(), tags=tags)
        state["memories"].append(self.memory_retriever.enrich_memory(asdict(memory)))
        self.store.save(state)
        return memory

    def list_memories(self) -> list[dict[str, Any]]:
        state = self.store.load()
        memories = sorted(state["memories"], key=lambda item: item["created_at"], reverse=True)
        return [self._public_memory(memory) for memory in memories]

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

    def retrieve_memories(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        state = self.store.load()
        return self.memory_retriever.retrieve(state.get("memories", []), query, limit)

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

        latest_memory = self._latest_memory(state)
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

    def daily_review(
        self,
        user_name: str = "User",
        now: datetime | None = None,
        use_llm: bool = False,
        include_prompt: bool = False,
    ) -> dict[str, Any]:
        now = now or utc_now()
        context = self._build_daily_review_context(user_name, now)
        template_review = self._render_template_daily_review(context)
        system_prompt, user_prompt = self._build_daily_review_prompt(context)
        llm_info = self._empty_llm_info(use_llm)

        review_text = template_review
        if use_llm:
            if self.llm is None:
                llm_info["error"] = "LLM client is not configured."
            else:
                try:
                    review_text = self.llm.generate(system_prompt, user_prompt)
                    llm_info["used"] = True
                except LLMError as error:
                    llm_info["error"] = str(error)

        response = {
            "generated_at": isoformat(now),
            "user_name": user_name,
            "date": context["date_text"],
            "completed_goals": context["completed_goals"],
            "pending_goals": context["pending_goals"],
            "today_check_ins": context["today_check_ins"],
            "relevant_memories": context["relevant_memories"],
            "memory_retrieval": context["memory_retrieval"],
            "reminders": context["reminders"],
            "tomorrow_priorities": context["tomorrow_priorities"],
            "review": review_text,
            "llm": llm_info,
        }

        if include_prompt:
            response["prompt"] = {
                "system": system_prompt,
                "user": user_prompt,
            }

        return response

    def daily_briefing(
        self,
        user_name: str = "User",
        weather: str | None = None,
        now: datetime | None = None,
        use_llm: bool = False,
        include_prompt: bool = False,
    ) -> dict[str, Any]:
        now = now or utc_now()
        context = self._build_briefing_context(user_name, weather, now)
        template_briefing = self._render_template_briefing(context)
        system_prompt, user_prompt = self._build_briefing_prompt(context)
        llm_info = self._empty_llm_info(use_llm)

        briefing = template_briefing
        if use_llm:
            if self.llm is None:
                llm_info["error"] = "LLM client is not configured."
            else:
                try:
                    briefing = self.llm.generate(system_prompt, user_prompt)
                    llm_info["used"] = True
                except LLMError as error:
                    llm_info["error"] = str(error)

        response = {
            "generated_at": isoformat(now),
            "user_name": user_name,
            "today": {
                "date": context["date_text"],
                "weather": context["weather_text"],
            },
            "important_goals": context["important_goals"],
            "relevant_memories": context["relevant_memories"],
            "memory_retrieval": context["memory_retrieval"],
            "reminders": context["reminders"],
            "suggestion": context["suggestion"],
            "briefing": briefing,
            "llm": llm_info,
        }

        if include_prompt:
            response["prompt"] = {
                "system": system_prompt,
                "user": user_prompt,
            }

        return response

    def _build_daily_review_context(self, user_name: str, now: datetime) -> dict[str, Any]:
        state = self.store.load()
        active_goals = [goal for goal in state.get("goals", []) if goal.get("status") == "active"]
        today_check_ins: list[dict[str, Any]] = []
        completed_goals: list[dict[str, Any]] = []
        pending_goals: list[dict[str, Any]] = []

        for goal in active_goals:
            check_ins = self._check_ins_on_date(goal, now)
            if check_ins:
                goal_summary = dict(goal)
                goal_summary["today_check_ins"] = check_ins
                completed_goals.append(goal_summary)
                for check_in in check_ins:
                    today_check_ins.append({
                        "goal_id": goal["id"],
                        "goal_title": goal["title"],
                        "at": check_in["at"],
                        "note": check_in["note"],
                    })
            else:
                pending_goals.append(goal)

        reminders = self.proactive_review(now)["reminders"]
        memory_query = self._build_review_memory_query(user_name, completed_goals, pending_goals, today_check_ins, reminders)
        relevant_memories = self.memory_retriever.retrieve(state.get("memories", []), memory_query, limit=8)
        retrieval_strategy = "local_sparse_embedding"
        if not relevant_memories:
            relevant_memories = self._recent_memories(state, limit=8)
            retrieval_strategy = "recent_memory_fallback"

        tomorrow_priorities = self._tomorrow_priorities(pending_goals, completed_goals)
        return {
            "user_name": user_name,
            "date_text": f"{now.month}月{now.day}日",
            "completed_goals": completed_goals,
            "pending_goals": pending_goals,
            "today_check_ins": today_check_ins,
            "relevant_memories": relevant_memories,
            "memory_retrieval": {
                "query": memory_query,
                "strategy": retrieval_strategy,
                "limit": 8,
            },
            "reminders": reminders,
            "tomorrow_priorities": tomorrow_priorities,
        }

    def _render_template_daily_review(self, context: dict[str, Any]) -> str:
        lines = [
            f"晚上好，{context['user_name']}。",
            "",
            f"今天是 {context['date_text']}，这是你的晚间复盘：",
            "",
        ]

        if context["completed_goals"]:
            lines.append("今天有推进的目标：")
            for goal in context["completed_goals"]:
                notes = "；".join(check_in["note"] for check_in in goal.get("today_check_ins", []))
                lines.append(f"- {goal['title']}：{notes}")
        else:
            lines.append("今天还没有记录目标打卡。")

        lines.append("")
        if context["pending_goals"]:
            lines.append("还没有推进的目标：")
            for goal in context["pending_goals"][:5]:
                lines.append(f"- {goal['title']}")
        else:
            lines.append("所有活跃目标今天都有记录，节奏不错。")

        if context["reminders"]:
            lines.append("")
            lines.append("需要注意的提醒：")
            lines.extend(f"- {reminder}" for reminder in context["reminders"])

        lines.append("")
        lines.append("明天建议优先做：")
        for priority in context["tomorrow_priorities"]:
            lines.append(f"- {priority}")

        lines.extend(["", "今天先收尾，明天继续把最重要的一步往前推。"])
        return "\n".join(lines)

    def _build_briefing_context(
        self,
        user_name: str,
        weather: str | None,
        now: datetime,
    ) -> dict[str, Any]:
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
        weather_text = weather or "天气信息暂未接入"
        date_text = f"{now.month}月{now.day}日"
        memory_query = self._build_memory_query(user_name, weather_text, important_goals, reminders)
        relevant_memories = self.memory_retriever.retrieve(state.get("memories", []), memory_query, limit=8)
        retrieval_strategy = "local_sparse_embedding"
        if not relevant_memories:
            relevant_memories = self._recent_memories(state, limit=8)
            retrieval_strategy = "recent_memory_fallback"

        if important_goals:
            suggested_goal = important_goals[0]
            suggestion = (
                f"我建议你今天先推进「{suggested_goal['title']}」，"
                "先做一个 30 分钟的小任务。"
            )
        elif relevant_memories:
            suggestion = f"你最近记录过：{relevant_memories[0]['text']}。今天可以围绕它安排一个小行动。"
        else:
            suggestion = "今天可以先添加一个长期目标，让我开始帮你追踪。"

        return {
            "user_name": user_name,
            "date_text": date_text,
            "weather_text": weather_text,
            "important_goals": important_goals,
            "relevant_memories": relevant_memories,
            "memory_retrieval": {
                "query": memory_query,
                "strategy": retrieval_strategy,
                "limit": 8,
            },
            "reminders": reminders,
            "suggestion": suggestion,
        }

    def _render_template_briefing(self, context: dict[str, Any]) -> str:
        important_goals = context["important_goals"]
        lines = [
            f"早上好，{context['user_name']}。",
            "",
            f"今天是 {context['date_text']}，{context['weather_text']}。",
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

        lines.extend(["", context["suggestion"]])

        if context["reminders"]:
            lines.append("")
            lines.append("另外，我注意到：")
            lines.extend(f"- {reminder}" for reminder in context["reminders"])

        lines.extend(["", "今天不用做完所有事，先把最重要的一步往前推。"])
        return "\n".join(lines)

    def _build_daily_review_prompt(self, context: dict[str, Any]) -> tuple[str, str]:
        system_prompt = (
            "You are Nexus, a proactive personal AI life assistant. "
            "Write in Chinese. Create a concise evening reflection. "
            "Focus on what moved forward, what is stuck, and what should happen tomorrow. "
            "Do not invent tasks or external data that were not provided."
        )
        memories = self._format_items(
            context["relevant_memories"],
            lambda item: (
                f"- {item['text']} (tags: {', '.join(item.get('tags', [])) or 'none'}; "
                f"score: {item.get('retrieval_score', 'fallback')})"
            ),
        )
        completed = self._format_items(
            context["completed_goals"],
            lambda goal: f"- {goal['title']} | check-ins: {self._format_check_in_notes(goal.get('today_check_ins', []))}",
        )
        pending = self._format_items(
            context["pending_goals"],
            lambda goal: f"- {goal['title']} | description: {goal.get('description') or 'none'}",
        )
        reminders = self._format_items(context["reminders"], lambda item: f"- {item}")
        priorities = self._format_items(context["tomorrow_priorities"], lambda item: f"- {item}")

        user_prompt = f"""Generate an evening daily review for {context['user_name']}.

Date: {context['date_text']}

Memory retrieval:
- Strategy: {context['memory_retrieval']['strategy']}
- Query: {context['memory_retrieval']['query']}

Relevant long-term memories:
{memories}

Goals with check-ins today:
{completed}

Goals without check-ins today:
{pending}

Proactive reminders:
{reminders}

Suggested tomorrow priorities:
{priorities}

Output format:
1. Today summary
2. Completed / moved forward
3. Stuck or quiet goals
4. Tomorrow's top priorities
5. One short closing note
"""
        return system_prompt, user_prompt

    def _build_briefing_prompt(self, context: dict[str, Any]) -> tuple[str, str]:
        system_prompt = (
            "You are Nexus, a proactive personal AI life assistant. "
            "Write in Chinese. Be concise, warm, concrete, and action-oriented. "
            "Do not invent calendar, weather, health, or email data that is not provided. "
            "Use retrieved long-term memories only when they are relevant. "
            "Turn goals into small next actions."
        )
        memories = self._format_items(
            context["relevant_memories"],
            lambda item: (
                f"- {item['text']} (tags: {', '.join(item.get('tags', [])) or 'none'}; "
                f"score: {item.get('retrieval_score', 'fallback')})"
            ),
        )
        goals = self._format_items(
            context["important_goals"],
            lambda item: (
                f"- {item['title']} | description: {item.get('description') or 'none'} | "
                f"cadence_days: {item.get('cadence_days')} | last_check_in: {item.get('last_check_in') or 'never'}"
            ),
        )
        reminders = self._format_items(context["reminders"], lambda item: f"- {item}")

        user_prompt = f"""Generate a morning briefing for {context['user_name']}.

Today:
- Date: {context['date_text']}
- Weather: {context['weather_text']}

Memory retrieval:
- Strategy: {context['memory_retrieval']['strategy']}
- Query: {context['memory_retrieval']['query']}

Relevant long-term memories:
{memories}

Important active goals:
{goals}

Proactive reminders:
{reminders}

Baseline suggestion:
- {context['suggestion']}

Output format:
1. Greeting
2. Today overview
3. Important things
4. Suggested first action
5. One short encouragement
"""
        return system_prompt, user_prompt

    @staticmethod
    def _format_items(items: list[Any], formatter: Any) -> str:
        if not items:
            return "- none"
        return "\n".join(formatter(item) for item in items)

    @staticmethod
    def _format_check_in_notes(check_ins: list[dict[str, Any]]) -> str:
        if not check_ins:
            return "none"
        return "; ".join(check_in.get("note", "") for check_in in check_ins)

    @staticmethod
    def _build_memory_query(
        user_name: str,
        weather_text: str,
        important_goals: list[dict[str, Any]],
        reminders: list[str],
    ) -> str:
        goal_text = " ".join(
            f"{goal.get('title', '')} {goal.get('description', '')}"
            for goal in important_goals
        )
        reminder_text = " ".join(reminders)
        return f"{user_name} morning briefing {weather_text} {goal_text} {reminder_text}".strip()

    @staticmethod
    def _build_review_memory_query(
        user_name: str,
        completed_goals: list[dict[str, Any]],
        pending_goals: list[dict[str, Any]],
        today_check_ins: list[dict[str, Any]],
        reminders: list[str],
    ) -> str:
        completed_text = " ".join(goal.get("title", "") for goal in completed_goals)
        pending_text = " ".join(goal.get("title", "") for goal in pending_goals)
        check_in_text = " ".join(check_in.get("note", "") for check_in in today_check_ins)
        reminder_text = " ".join(reminders)
        return f"{user_name} evening review reflection {completed_text} {pending_text} {check_in_text} {reminder_text}".strip()

    @staticmethod
    def _check_ins_on_date(goal: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
        check_ins = []
        for check_in in goal.get("check_ins", []):
            check_in_time = parse_timestamp(check_in.get("at"))
            if check_in_time and check_in_time.astimezone(UTC).date() == now.astimezone(UTC).date():
                check_ins.append(check_in)
        return check_ins

    @staticmethod
    def _tomorrow_priorities(
        pending_goals: list[dict[str, Any]],
        completed_goals: list[dict[str, Any]],
    ) -> list[str]:
        priorities = [f"继续推进「{goal['title']}」，先完成一个 30 分钟的小任务。" for goal in pending_goals[:3]]
        if not priorities:
            priorities = [f"巩固今天已经推进的「{goal['title']}」，记录下一步。" for goal in completed_goals[:3]]
        if not priorities:
            priorities = ["明天先添加一个明确目标，让 Nexus 开始帮你追踪。"]
        return priorities

    @staticmethod
    def _empty_llm_info(requested: bool) -> dict[str, Any]:
        return {
            "requested": requested,
            "used": False,
            "error": None,
        }

    @staticmethod
    def _public_memory(memory: dict[str, Any]) -> dict[str, Any]:
        public = dict(memory)
        public.pop("embedding", None)
        return public

    @staticmethod
    def _latest_memory(state: dict[str, Any]) -> dict[str, Any] | None:
        memories = state.get("memories", [])
        if not memories:
            return None
        return max(memories, key=lambda item: item["created_at"])

    @staticmethod
    def _recent_memories(state: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        memories = state.get("memories", [])
        public_memories = [NexusService._public_memory(memory) for memory in memories]
        return sorted(public_memories, key=lambda item: item["created_at"], reverse=True)[:limit]

    @staticmethod
    def _goal_to_dict(goal: Goal) -> dict[str, Any]:
        data = asdict(goal)
        data["check_ins"] = [asdict(check_in) for check_in in goal.check_ins]
        return data

