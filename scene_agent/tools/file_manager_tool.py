"""LangChain tools for inspecting and managing files inside a Godot project.

Exposes three small, safe tools that the scene-generation ReAct agent uses
to orient itself before (and while) writing scripts:

* ``list_project_files`` — enumerate the existing tree under ``res://``.
* ``read_project_file`` — read a single file (size-capped).
* ``ensure_project_directory`` — create directories before writing into them.

All paths are resolved relative to ``GODOT_PROJECT_PATH``; ``res://`` URIs
are accepted everywhere.
"""

from __future__ import annotations

import os
from pathlib import Path

from langchain_core.tools import tool

_MAX_LIST_ENTRIES = 200
_MAX_READ_BYTES = 200_000


def _resolve(path: str) -> Path:
    """Resolve a Godot-style or relative path to an absolute filesystem path."""
    cleaned = (path or "").strip().replace("\\", "/")
    project_root = Path(os.getenv("GODOT_PROJECT_PATH", "")).expanduser()
    if not project_root.parts:
        project_root = Path.cwd()

    if cleaned in ("", "res://"):
        return project_root
    if cleaned.startswith("res://"):
        return project_root / cleaned[len("res://"):]

    candidate = Path(cleaned)
    if candidate.is_absolute():
        return candidate
    return project_root / cleaned


@tool("list_project_files")
def list_project_files(directory: str = "res://") -> str:
    """List files and directories under a Godot project path.

    Args:
        directory: ``res://`` URI or relative path. Defaults to the project root.

    Returns:
        A newline-separated listing (max 200 entries), each prefixed with
        ``DIR `` or ``FILE``, or an error string.
    """
    target = _resolve(directory)
    if not target.exists():
        return f"NOT_FOUND: {directory}"
    if not target.is_dir():
        return f"NOT_A_DIR: {directory}"

    entries: list[str] = []
    for child in sorted(target.iterdir()):
        marker = "DIR " if child.is_dir() else "FILE"
        entries.append(f"{marker} {child.relative_to(target).as_posix()}")
        if len(entries) >= _MAX_LIST_ENTRIES:
            entries.append("... (truncated)")
            break
    return "\n".join(entries) if entries else "(empty directory)"


@tool("read_project_file")
def read_project_file(file_path: str) -> str:
    """Return the textual contents of a file inside the Godot project.

    Args:
        file_path: ``res://`` URI, absolute, or relative path.

    Returns:
        The UTF-8 file contents (truncated to 200 KB) or an error message.
    """
    target = _resolve(file_path)
    if not target.exists():
        return f"NOT_FOUND: {file_path}"
    if not target.is_file():
        return f"NOT_A_FILE: {file_path}"
    try:
        size = target.stat().st_size
        if size > _MAX_READ_BYTES:
            return f"FILE_TOO_LARGE: {file_path} ({size} bytes)"
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"BINARY_FILE: {file_path}"
    except OSError as exc:
        return f"READ_ERROR {file_path}: {exc}"


@tool("ensure_project_directory")
def ensure_project_directory(directory: str) -> str:
    """Create the given directory inside the Godot project if it doesn't exist.

    Args:
        directory: ``res://`` URI or relative path to create. Parent
            directories are created as needed.

    Returns:
        A short status string.
    """
    target = _resolve(directory)
    try:
        target.mkdir(parents=True, exist_ok=True)
        return f"OK: ensured directory {target}"
    except OSError as exc:
        return f"MKDIR_ERROR {directory}: {exc}"
