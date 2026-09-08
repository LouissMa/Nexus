from __future__ import annotations

import os
from pathlib import Path
from time import monotonic
from typing import Any

from nexus.integrations.core import ToolError


def find_local_files(roots: list[Path], query: str) -> dict[str, Any]:
    """Search names only; cap entries, time, results, and directory traversal."""
    query = query.strip().casefold()
    if not query or len(query) > 200:
        raise ToolError("File query must contain 1 to 200 characters.")
    terms = [query]
    if query in {"护照", "护照照片", "passport", "passport photo", "passport photos"}:
        terms = ["护照", "passport"]
    pending = list(roots)
    matches: list[dict[str, Any]] = []
    visited: set[Path] = set()
    scanned = 0
    skipped = 0
    deadline = monotonic() + 5
    while pending and scanned < 10000 and len(matches) < 50 and monotonic() < deadline:
        directory = pending.pop()
        try:
            resolved = directory.resolve(strict=True)
            if resolved in visited or not any(resolved == root or resolved.is_relative_to(root) for root in roots):
                continue
            visited.add(resolved)
            with os.scandir(resolved) as entries:
                for entry in entries:
                    if scanned >= 10000 or len(matches) >= 50 or monotonic() >= deadline:
                        return {"matches": matches, "scanned": scanned, "truncated": True, "skipped": skipped}
                    scanned += 1
                    if entry.name.startswith(".") or entry.is_symlink():
                        continue
                    path = Path(entry.path)
                    if getattr(path, "is_junction", lambda: False)():
                        continue
                    target = path.resolve(strict=True)
                    if not any(target.is_relative_to(root) for root in roots):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name.casefold() not in {"node_modules", "__pycache__", "$recycle.bin"}:
                            pending.append(target)
                    elif entry.is_file(follow_symlinks=False) and any(term in entry.name.casefold() for term in terms):
                        stat = entry.stat(follow_symlinks=False)
                        matches.append({"path": str(target), "name": entry.name, "bytes": stat.st_size,
                                        "modified": stat.st_mtime})
        except OSError:
            skipped += 1
    return {"matches": matches, "scanned": scanned, "truncated": bool(pending), "skipped": skipped}


class DesktopTaskService:
    def __init__(self, tools: Any, automations: Any, *, opener: Any = None):
        self.tools = tools
        self.automations = automations
        self.opener = opener
        self.candidates: list[dict[str, Any]] = []

    def search(self, query: str) -> dict[str, Any]:
        self.candidates = []
        settings = self.tools.settings.get("filesystem", {})
        roots = settings.get("roots", [])
        self.tools.policy.require("filesystem", "search")
        if not roots:
            raise ToolError("Configure filesystem roots with nexus config tool set filesystem --root first.")
        matches = []
        truncated = False
        skipped = 0
        for root in roots[:10]:
            data = self.tools.execute("filesystem", "search", path=root, query=query, mode="filename").data
            matches.extend(data["matches"])
            truncated = truncated or data["truncated"]
            skipped += data["skipped"]
        unique = {item["path"]: item for item in matches}
        self.candidates = list(unique.values())[:50]
        return {"matches": [{"number": i + 1, **item} for i, item in enumerate(self.candidates)],
                "truncated": truncated or len(unique) > 50 or len(roots) > 10,
                "strategy": "filename", "configured_roots": len(roots), "skipped_directories": skipped}

    def candidate(self, number: int) -> str:
        if not 1 <= number <= len(self.candidates):
            raise ToolError("No matching candidate in this conversation; search again or supply an explicit path.")
        return self.candidates[number - 1]["path"]

    def open_file(self, value: str, *, approved: bool) -> dict[str, Any]:
        if not approved:
            raise ToolError("Opening a file requires approval.")
        self.tools.policy.require("filesystem", "read")
        roots = [Path(root).expanduser().resolve() for root in self.tools.settings["filesystem"].get("roots", [])]
        path = Path(value).expanduser().resolve(strict=True)
        if not path.is_file() or not any(path.is_relative_to(root) for root in roots):
            raise ToolError("File is outside authorized roots or is not a regular file.")
        if path.suffix.casefold() not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".pdf", ".txt", ".md"}:
            raise ToolError("Only supported image, PDF, and plain-text files can be opened.")
        if self.opener is None and os.name != "nt":
            raise ToolError("Local file opening currently requires Windows.")
        (self.opener or os.startfile)(str(path))
        self.tools.audit_logger.record(tool="filesystem", operation="open", arguments={}, status="success")
        return {"path": str(path), "status": "launch_requested", "verified": "file_exists"}

    def launch(self, name: str, *, approved: bool) -> dict[str, Any]:
        aliases = {key.casefold(): key for key in self.automations.settings}
        key = aliases.get(name.strip().casefold())
        if key is None:
            raise ToolError("Register this application or website with nexus automation set first.")
        if self.automations.settings[key]["type"] not in {"browser", "application"}:
            raise ToolError("The open intent accepts only registered applications and websites.")
        return self.automations.run(key, approved=approved)


def build_desktop_service() -> DesktopTaskService:
    from nexus.automation import AutomationManager, load_automation_settings
    from nexus.config import load_tool_settings, nexus_home
    from nexus.integrations.manager import build_tool_manager
    from nexus.store import JsonStore

    home = nexus_home()
    tools = build_tool_manager(load_tool_settings(), home)
    return DesktopTaskService(tools, AutomationManager(load_automation_settings(), home, JsonStore.from_env(), tool_manager=tools))
