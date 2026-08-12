from __future__ import annotations

from pathlib import Path
import sys

import pytest

from nexus.research import ResearchService
from nexus.research_experiments import ExperimentError, RestrictedExperimentRunner
from nexus.store import JsonStore


def runner(
    tmp_path: Path,
) -> tuple[RestrictedExperimentRunner, ResearchService, str, Path]:
    store = JsonStore(tmp_path / "home" / "state.json")
    research = ResearchService(store)
    project = research.create("Experiment", "Run a bounded validation.")
    root = tmp_path / "workspace"
    root.mkdir()
    return (
        RestrictedExperimentRunner(
            research,
            allowed_root=root,
            allowed_executables={Path(sys.executable).name.casefold()},
            output_limit=256,
        ),
        research,
        project["id"],
        root,
    )


def test_experiment_requires_approval_and_allowed_root(tmp_path: Path) -> None:
    service, research, project_id, root = runner(tmp_path)

    with pytest.raises(ExperimentError, match="approval"):
        service.run(project_id, [sys.executable, "-c", "print('no')"], root)
    with pytest.raises(ExperimentError, match="outside"):
        service.run(
            project_id,
            [sys.executable, "-c", "print('no')"],
            tmp_path,
            approved=True,
        )

    assert research.show(project_id)["experiments"] == []


def test_experiment_preserves_arguments_caps_output_and_persists(
    tmp_path: Path,
) -> None:
    service, research, project_id, root = runner(tmp_path)
    marker = "value with spaces; echo not-a-shell"

    result = service.run(
        project_id,
        [
            sys.executable,
            "-c",
            "import sys; print(sys.argv[1]); print('x'*500)",
            marker,
        ],
        root,
        approved=True,
        timeout_seconds=5,
    )

    assert result["status"] == "completed"
    assert marker in result["stdout"]
    assert result["stdout_truncated"] is True
    stored = research.show(project_id)["experiments"][0]
    assert stored["status"] == "completed"
    assert "restricted runner" in stored["method"]


def test_experiment_rejects_executable_and_times_out(tmp_path: Path) -> None:
    service, research, project_id, root = runner(tmp_path)
    with pytest.raises(ExperimentError, match="allowlist"):
        service.run(project_id, ["not-allowed", "--version"], root, approved=True)

    result = service.run(
        project_id,
        [sys.executable, "-c", "import time; time.sleep(2)"],
        root,
        approved=True,
        timeout_seconds=0.1,
    )

    assert result["status"] == "blocked"
    assert result["timed_out"] is True
    assert research.show(project_id)["experiments"][0]["status"] == "blocked"
