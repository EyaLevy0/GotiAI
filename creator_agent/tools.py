"""Tools for the Creator Agent (A2)."""

from __future__ import annotations

import os
from pathlib import Path

from langchain_core.tools import tool


def _resolve_project_path(file_path: str) -> Path:
	"""Translate Godot ``res://`` paths to filesystem paths under GODOT_PROJECT_PATH.

	Also strips Windows-invalid characters and rejects empty paths.
	"""
	cleaned = file_path.strip().replace("\\", "/")
	project_root = Path(os.getenv("GODOT_PROJECT_PATH", "")).expanduser()
	if not project_root.parts:
		project_root = Path.cwd()

	if cleaned.startswith("res://"):
		rel = cleaned[len("res://"):]
		return project_root / rel

	candidate = Path(cleaned)
	if candidate.is_absolute():
		return candidate
	return project_root / cleaned


@tool
def write_gdscript(file_path: str, code: str) -> str:
	"""Write GDScript or any Godot project file to the given path.

	Accepts either an absolute path, a path relative to the Godot project root,
	or a Godot ``res://`` URI. Creates any missing parent directories.
	"""
	try:
		target = _resolve_project_path(file_path)
		target.parent.mkdir(parents=True, exist_ok=True)
		target.write_text(code, encoding="utf-8")
		return f"Successfully wrote file: {target}"
	except OSError as exc:
		return f"ERROR_WRITING_FILE {file_path}: {exc}"
