from __future__ import annotations

from copy import deepcopy
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from .store import JsonStore


PROJECT_STATUSES = ("active", "paused", "completed", "archived")
MILESTONE_STATUSES = ("pending", "in_progress", "completed")
MAX_PROJECTS = 200
MAX_MILESTONES = 200
MAX_PROGRESS_ENTRIES = 500
MAX_TEXT_LENGTH = 1_000


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(microsecond=0).isoformat()


def _text(value: str, field: str, *, required: bool = False) -> str:
    result = str(value).strip()
    if required and not result:
        raise ValueError(f"{field} is required.")
    if len(result) > MAX_TEXT_LENGTH:
        raise ValueError(f"{field} must be at most {MAX_TEXT_LENGTH} characters.")
    return result


def _date(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD.") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must use YYYY-MM-DD.")
    return value


def _ids(values: tuple[str, ...] | list[str]) -> list[str]:
    result = []
    for value in values:
        item = str(value).strip()
        if item and item not in result:
            result.append(item[:100])
        if len(result) >= 100:
            break
    return result


def project_summary(project: dict[str, Any]) -> dict[str, Any]:
    milestones = [
        item for item in project.get("milestones", []) if isinstance(item, dict)
    ]
    completed = sum(item.get("status") == "completed" for item in milestones)
    if milestones:
        progress = round(completed * 100 / len(milestones))
        source = "milestones"
    else:
        entries = [
            item
            for item in project.get("progress_entries", [])
            if isinstance(item, dict)
        ]
        progress = int(entries[-1].get("percent", 0)) if entries else 0
        source = "explicit"
    return {
        "progress_percent": progress,
        "progress_source": source,
        "milestone_count": len(milestones),
        "completed_milestones": completed,
    }


class ProjectService:
    def __init__(self, store: JsonStore) -> None:
        self.store = store

    def add(
        self,
        name: str,
        description: str,
        priority: int,
        target_date: str | None,
        goal_ids: tuple[str, ...] | list[str],
        task_ids: tuple[str, ...] | list[str],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(priority, int)
            or isinstance(priority, bool)
            or priority < 1
            or priority > 5
        ):
            raise ValueError("priority must be an integer from 1 to 5.")
        timestamp = _iso_utc(now or datetime.now(UTC))
        project = {
            "id": uuid4().hex[:8],
            "name": _text(name, "name", required=True),
            "description": _text(description, "description"),
            "status": "active",
            "priority": priority,
            "target_date": _date(target_date, "target_date"),
            "goal_ids": _ids(goal_ids),
            "task_ids": _ids(task_ids),
            "milestones": [],
            "progress_entries": [],
            "created_at": timestamp,
            "updated_at": timestamp,
            "archived_at": None,
        }

        def mutation(state: dict[str, Any]) -> dict[str, Any]:
            collection = state.setdefault("projects", [])
            if len(collection) >= MAX_PROJECTS:
                raise ValueError(f"At most {MAX_PROJECTS} projects are supported.")
            collection.append(deepcopy(project))
            return deepcopy(project)

        return self.store.mutate(mutation)

    def list(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        projects = []
        for raw in self.store.load().get("projects", []):
            if not isinstance(raw, dict):
                continue
            if not include_archived and raw.get("status") == "archived":
                continue
            project = deepcopy(raw)
            project["summary"] = project_summary(project)
            projects.append(project)
        return sorted(
            projects,
            key=lambda item: (
                item.get("status") == "archived",
                item.get("priority", 5),
                item.get("target_date") or "9999-12-31",
                item.get("name", "").casefold(),
            ),
        )

    def add_milestone(
        self,
        project_id: str,
        title: str,
        target_date: str | None,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = _iso_utc(now or datetime.now(UTC))
        milestone = {
            "id": uuid4().hex[:8],
            "title": _text(title, "title", required=True),
            "status": "pending",
            "target_date": _date(target_date, "target_date"),
            "created_at": timestamp,
            "updated_at": timestamp,
        }

        def mutation(state: dict[str, Any]) -> dict[str, Any]:
            project = self._find(state, project_id)
            collection = project.setdefault("milestones", [])
            if len(collection) >= MAX_MILESTONES:
                raise ValueError(f"At most {MAX_MILESTONES} milestones are supported.")
            collection.append(deepcopy(milestone))
            project["updated_at"] = timestamp
            return deepcopy(project)

        project = self.store.mutate(mutation)
        return {
            "project": project,
            "milestone": deepcopy(milestone),
            "summary": project_summary(project),
        }

    def update_milestone(
        self,
        project_id: str,
        milestone_id: str,
        status: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if status not in MILESTONE_STATUSES:
            raise ValueError("status must be pending, in_progress, or completed.")
        timestamp = _iso_utc(now or datetime.now(UTC))

        def mutation(state: dict[str, Any]) -> dict[str, Any]:
            project = self._find(state, project_id)
            for milestone in project.setdefault("milestones", []):
                if milestone.get("id") == milestone_id:
                    milestone["status"] = status
                    milestone["updated_at"] = timestamp
                    project["updated_at"] = timestamp
                    return {
                        "project": deepcopy(project),
                        "milestone": deepcopy(milestone),
                    }
            raise ValueError(f"Milestone '{milestone_id}' not found.")

        result = self.store.mutate(mutation)
        result["summary"] = project_summary(result["project"])
        return result

    def update_progress(
        self,
        project_id: str,
        percent: int,
        note: str,
        correction: bool,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(percent, int)
            or isinstance(percent, bool)
            or percent < 0
            or percent > 100
        ):
            raise ValueError("percent must be an integer from 0 to 100.")
        timestamp = _iso_utc(now or datetime.now(UTC))
        clean_note = _text(note, "note")

        def mutation(state: dict[str, Any]) -> dict[str, Any]:
            project = self._find(state, project_id)
            entries = project.setdefault("progress_entries", [])
            previous = int(entries[-1].get("percent", 0)) if entries else 0
            if percent < previous and not correction:
                raise ValueError(
                    "Lower progress requires the explicit correction flag."
                )
            entries.append(
                {
                    "percent": percent,
                    "note": clean_note,
                    "correction": bool(correction),
                    "at": timestamp,
                }
            )
            del entries[:-MAX_PROGRESS_ENTRIES]
            project["updated_at"] = timestamp
            return deepcopy(project)

        project = self.store.mutate(mutation)
        return {"project": project, "summary": project_summary(project)}

    def archive(
        self,
        project_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = _iso_utc(now or datetime.now(UTC))

        def mutation(state: dict[str, Any]) -> dict[str, Any]:
            project = self._find(state, project_id)
            project["status"] = "archived"
            project["archived_at"] = timestamp
            project["updated_at"] = timestamp
            return deepcopy(project)

        return self.store.mutate(mutation)

    @staticmethod
    def _find(state: dict[str, Any], project_id: str) -> dict[str, Any]:
        for project in state.setdefault("projects", []):
            if project.get("id") == project_id:
                return project
        raise ValueError(f"Project '{project_id}' not found.")
