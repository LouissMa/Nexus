from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4


COACH_MODES = ("strict", "gentle", "academic", "startup")
TASK_STATUSES = ("pending", "in_progress", "completed", "blocked")


@dataclass(frozen=True)
class CoachProfile:
    mode: str
    label: str
    instruction: str
    closing: str


COACH_PROFILES = {
    "strict": CoachProfile(
        "strict",
        "strict execution coach",
        "Be direct, concise, accountable, and focused on concrete completion.",
        "Start with today's most important action and finish it before adding more.",
    ),
    "gentle": CoachProfile(
        "gentle",
        "gentle supportive coach",
        "Be warm, realistic, non-judgmental, and reduce tasks when energy is limited.",
        "A small realistic step still counts as meaningful progress.",
    ),
    "academic": CoachProfile(
        "academic",
        "academic study coach",
        "Emphasize learning outcomes, deliberate practice, evidence, and review.",
        "Record the result and open questions so the next practice is more focused.",
    ),
    "startup": CoachProfile(
        "startup",
        "startup execution coach",
        "Emphasize validation, shipping, user value, and the smallest useful deliverable.",
        "Ship one testable outcome, learn from it, and then iterate.",
    ),
}


def coach_profile(mode: str) -> CoachProfile:
    if mode not in COACH_PROFILES:
        raise ValueError(f"Unknown coach mode '{mode}'.")
    return COACH_PROFILES[mode]


def build_daily_tasks(
    goals: list[dict[str, Any]],
    plan_date: str,
    created_at: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for priority, goal in enumerate(goals[:limit], start=1):
        description = (goal.get("description") or "").strip()
        tasks.append(
            {
                "id": str(uuid4())[:8],
                "plan_date": plan_date,
                "goal_id": goal["id"],
                "goal_title": goal["title"],
                "title": description
                or f"Advance '{goal['title']}' and record one verifiable result",
                "priority": priority,
                "estimated_minutes": 30,
                "status": "pending",
                "blocker": None,
                "unresolved": [],
                "notes": [],
                "created_at": created_at,
                "updated_at": None,
            }
        )
    return tasks
