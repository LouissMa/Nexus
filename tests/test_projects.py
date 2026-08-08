from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.projects import ProjectService
from nexus.store import JsonStore


NOW = datetime(2026, 8, 8, 9, 0, tzinfo=UTC)


def service(tmp_path: Path) -> ProjectService:
    return ProjectService(JsonStore(tmp_path / "state.json"))


def test_add_project_validates_priority_date_and_links(tmp_path: Path) -> None:
    projects = service(tmp_path)
    with pytest.raises(ValueError, match="priority"):
        projects.add("Nexus", "", 0, None, (), (), now=NOW)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        projects.add("Nexus", "", 3, "08/30/2026", (), (), now=NOW)

    project = projects.add(
        "Nexus",
        "Adaptive life workspace",
        1,
        "2026-08-30",
        ("goal-a", "goal-b"),
        ("task-a",),
        now=NOW,
    )

    assert project["priority"] == 1
    assert project["target_date"] == "2026-08-30"
    assert project["goal_ids"] == ["goal-a", "goal-b"]
    assert project["task_ids"] == ["task-a"]
    assert project["milestones"] == []


def test_milestones_drive_project_progress(tmp_path: Path) -> None:
    projects = service(tmp_path)
    project = projects.add("Nexus", "", 1, None, (), (), now=NOW)
    first = projects.add_milestone(project["id"], "Domain", None, now=NOW)
    second = projects.add_milestone(project["id"], "Dashboard", "2026-08-20", now=NOW)

    updated = projects.update_milestone(
        project["id"], first["milestone"]["id"], "completed", now=NOW
    )
    listed = projects.list()

    assert second["milestone"]["status"] == "pending"
    assert updated["summary"]["progress_percent"] == 50
    assert listed[0]["summary"]["completed_milestones"] == 1
    assert listed[0]["summary"]["milestone_count"] == 2


def test_explicit_progress_is_monotonic_without_correction(tmp_path: Path) -> None:
    projects = service(tmp_path)
    project = projects.add("Research", "", 2, None, (), (), now=NOW)
    first = projects.update_progress(project["id"], 60, "prototype", False, now=NOW)

    with pytest.raises(ValueError, match="correction"):
        projects.update_progress(project["id"], 40, "re-estimated", False, now=NOW)

    corrected = projects.update_progress(
        project["id"], 40, "scope changed", True, now=NOW
    )

    assert first["summary"]["progress_percent"] == 60
    assert corrected["summary"]["progress_percent"] == 40
    assert corrected["project"]["progress_entries"][-1]["correction"] is True


def test_archive_hides_project_and_legacy_state_normalizes(tmp_path: Path) -> None:
    store = JsonStore(tmp_path / "state.json")
    assert store.load()["projects"] == []
    projects = ProjectService(store)
    project = projects.add("Nexus", "", 1, None, (), (), now=NOW)

    archived = projects.archive(project["id"], now=NOW)

    assert archived["status"] == "archived"
    assert projects.list() == []
    assert projects.list(include_archived=True)[0]["id"] == project["id"]


def test_project_operations_reject_unknown_ids_and_invalid_progress(
    tmp_path: Path,
) -> None:
    projects = service(tmp_path)
    project = projects.add("Nexus", "", 1, None, (), (), now=NOW)
    milestone = projects.add_milestone(project["id"], "One", None, now=NOW)

    with pytest.raises(ValueError, match="not found"):
        projects.update_progress("missing", 10, "", False, now=NOW)
    with pytest.raises(ValueError, match="percent"):
        projects.update_progress(project["id"], 101, "", False, now=NOW)
    with pytest.raises(ValueError, match="status"):
        projects.update_milestone(
            project["id"], milestone["milestone"]["id"], "unknown", now=NOW
        )
