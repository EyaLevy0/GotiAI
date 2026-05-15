"""LangChain tool for writing GDScript / TSCN files into a Godot project.

The agent invokes this tool with a Godot-style ``res://`` path or an absolute
filesystem path together with the textual file content. The tool resolves
``res://`` URIs against the ``GODOT_PROJECT_PATH`` environment variable, then
creates any missing parent directories and writes the file in UTF-8.
"""

from __future__ import annotations

import os
from pathlib import Path

from langchain_core.tools import tool


def _resolve_project_path(file_path: str) -> Path:
    """Translate Godot ``res://`` paths to filesystem paths under GODOT_PROJECT_PATH.

    Absolute paths are returned untouched. Relative paths and ``res://`` URIs
    are resolved against the ``GODOT_PROJECT_PATH`` environment variable, with
    the current working directory as a final fallback.
    """
    cleaned = file_path.strip().replace("\\", "/")
    project_root = Path(os.getenv("GODOT_PROJECT_PATH", "")).expanduser()
    if not project_root.parts:
        project_root = Path.cwd()

    if cleaned.startswith("res://"):
        return project_root / cleaned[len("res://"):]

    candidate = Path(cleaned)
    if candidate.is_absolute():
        return candidate
    return project_root / cleaned


@tool("write_code_file")
def write_code_file(file_path: str, code: str) -> str:
    """Write a GDScript or scene file to the Godot project.

    Args:
        file_path: Either a Godot ``res://`` URI (e.g. ``res://main.gd``),
            an absolute filesystem path, or a path relative to
            ``GODOT_PROJECT_PATH``.
        code: The full textual content to write. The file is overwritten
            atomically if it already exists.

    Returns:
        A short status string suitable for inclusion in a ReAct trace.
    """
    try:
        target = _resolve_project_path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code, encoding="utf-8")
        return f"OK: wrote {target} ({len(code)} chars)"
    except OSError as exc:
        return f"ERROR_WRITING_FILE {file_path}: {exc}"
