from __future__ import annotations

from pathlib import Path
import os
import subprocess
from time import monotonic
from typing import Any

from .research import ResearchService


class ExperimentError(ValueError):
    pass


class RestrictedExperimentRunner:
    def __init__(
        self,
        research: ResearchService,
        *,
        allowed_root: Path,
        allowed_executables: set[str],
        output_limit: int = 16_384,
    ) -> None:
        self.research = research
        self.allowed_root = allowed_root.expanduser().resolve()
        self.allowed_executables = {item.casefold() for item in allowed_executables}
        self.output_limit = max(256, min(int(output_limit), 100_000))

    def run(
        self,
        project_id: str,
        argv: list[str] | tuple[str, ...],
        cwd: str | Path,
        *,
        approved: bool = False,
        timeout_seconds: float = 30,
    ) -> dict[str, Any]:
        if not approved:
            raise ExperimentError("Explicit experiment approval is required.")
        command = [str(item) for item in argv]
        if not command or not command[0].strip():
            raise ExperimentError("Experiment command is required.")
        executable = Path(command[0]).name.casefold()
        if executable not in self.allowed_executables:
            raise ExperimentError(f"Executable '{executable}' is not in the allowlist.")
        working = Path(cwd).expanduser().resolve()
        if not working.is_dir() or not working.is_relative_to(self.allowed_root):
            raise ExperimentError(
                "Experiment working directory is outside the allowed root."
            )
        timeout = max(0.05, min(float(timeout_seconds), 300.0))
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
        started = monotonic()
        timed_out = False
        return_code: int | None
        try:
            completed = subprocess.run(
                command,
                cwd=working,
                env=environment,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            return_code = completed.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            return_code = None
            stdout = self._as_text(exc.stdout)
            stderr = self._as_text(exc.stderr)
        duration_ms = int((monotonic() - started) * 1000)
        stdout_value, stdout_truncated = self._cap(stdout)
        stderr_value, stderr_truncated = self._cap(stderr)
        status = "completed" if return_code == 0 and not timed_out else "blocked"
        summary = (
            f"exit={return_code}; timed_out={str(timed_out).lower()}; "
            f"duration_ms={duration_ms}; stdout={stdout_value}; stderr={stderr_value}"
        )[:4_000]
        stored = self.research.add_experiment(
            project_id,
            f"Restricted experiment: {executable}",
            "Validate a research hypothesis with an explicitly approved command.",
            "Executed by the Nexus restricted runner with shell disabled, an executable "
            "allowlist, a bounded working root, timeout, and output caps.",
            summary,
            status,
            [],
        )["experiment"]
        return {
            "experiment_id": stored["id"],
            "status": status,
            "executable": executable,
            "argument_count": max(0, len(command) - 1),
            "return_code": return_code,
            "timed_out": timed_out,
            "duration_ms": duration_ms,
            "stdout": stdout_value,
            "stderr": stderr_value,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "safety": "restricted_process_not_os_sandbox",
        }

    def _cap(self, value: str) -> tuple[str, bool]:
        if len(value) <= self.output_limit:
            return value, False
        return value[: self.output_limit], True

    @staticmethod
    def _as_text(value: bytes | str | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value
