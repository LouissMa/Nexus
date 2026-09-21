"""Create-only report artifacts for the approval-gated execution registry."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat


def _windows_drive_type(anchor):
    import ctypes

    get_type = ctypes.WinDLL("kernel32", use_last_error=True).GetDriveTypeW
    get_type.argtypes = [ctypes.c_wchar_p]
    get_type.restype = ctypes.c_uint
    return get_type(anchor)


def _checked_path(value):
    if not isinstance(value, str) or not value or len(value) > 2000:
        raise ValueError("An absolute local path is required.")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or str(path).startswith(("\\\\", "//")):
        raise ValueError("Relative, traversal and network paths are not allowed.")
    if os.name == "nt" and _windows_drive_type(path.anchor) not in {2, 3, 5, 6}:
        raise ValueError("A known local drive is required; remote drives are not allowed.")
    for part in path.parts[1:]:
        if (part.endswith((".", " "))
                or any(ord(c) < 32 or c in '<>:"|?*' for c in part)
                or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part, re.I)):
            raise ValueError("Unsafe path component.")
    for component in [*reversed(path.parents), path]:
        if component.is_symlink():
            raise ValueError("Linked report paths are not allowed.")
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            continue
        if getattr(metadata, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise ValueError("Reparse points are not allowed.")
    return path


def validate_report_roots(values):
    if not isinstance(values, list) or len(values) > 16:
        raise ValueError("Configure at most 16 report directories.")
    roots = []
    for value in values:
        path = _checked_path(value)
        if not path.is_dir() or path == Path(path.anchor):
            raise ValueError("Report roots must be existing non-volume-root directories.")
        if path not in roots:
            roots.append(path)
    return roots


def create_report(arguments, settings, *, approved=False):
    if approved is not True or settings.get("enabled") is not True:
        raise ValueError("Explicit approval and enabled filesystem configuration are required.")
    roots = validate_report_roots(settings.get("report_roots", []))
    target = _checked_path(arguments["path"])
    if not any(target.is_relative_to(root) and target != root
               and not any(part.startswith(".") for part in target.relative_to(root).parts) for root in roots):
        raise ValueError("Report path is outside the authorized output directories.")
    if target.suffix.lower() not in {".md", ".txt", ".json"} or not target.parent.is_dir():
        raise ValueError("Only Markdown, TXT or JSON in an existing directory is supported.")
    content = arguments["content"]
    if not isinstance(content, str) or not content.strip() or "\x00" in content:
        raise ValueError("Nonempty text is required.")
    data = content.encode("utf-8")
    if len(data) > 12000:
        raise ValueError("Report exceeds 12000 UTF-8 bytes.")
    if target.suffix.lower() == ".json":
        def reject_constant(value):
            raise ValueError("JSON constants must be finite.")
        json.loads(content, parse_constant=reject_constant)
    # Exclusive creation never replaces existing files. Incomplete writes remain
    # visible for manual reconciliation; do not delete/replay uncertain effects.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(target, flags, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    return {"path": str(target), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "created": True}
