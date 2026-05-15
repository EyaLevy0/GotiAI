"""Tools for the Creator Agent (A2)."""

from __future__ import annotations

import os
from pathlib import Path

from langchain_core.tools import tool


def _resolve_target_path(file_path: str, project_path: str) -> Path:
	"""Resolve tool file paths to real filesystem targets.

	Supports:
	- Godot-style paths (`res://main.gd`) resolved under `project_path`
	- absolute filesystem paths (used as-is)
	- relative paths (resolved under `project_path` when provided)
	"""
	path_str = file_path.strip()
	if path_str.startswith("res://"):
		if not project_path:
			raise ValueError("project_path is required when writing res:// paths")
		rel = path_str[len("res://") :].lstrip("/")
		return Path(project_path) / rel

	target = Path(path_str)
	if target.is_absolute():
		return target

	if project_path:
		return Path(project_path) / target
	return target


@tool
def write_gdscript(file_path: str, code: str) -> str:
	"""Write GDScript or any Godot project file to the given path.

	Creates any missing parent directories before writing.
	"""
	project_path = os.getenv("GODOT_PROJECT_PATH", "")
	target = _resolve_target_path(file_path, project_path)
	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_text(code, encoding="utf-8")
	return f"Successfully wrote file: {target}"
