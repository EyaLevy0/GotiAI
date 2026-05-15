"""Tools for the Creator Agent (A2)."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool


@tool
def write_gdscript(file_path: str, code: str) -> str:
	"""Write GDScript or any Godot project file to the given path.

	Creates any missing parent directories before writing.
	"""
	target = Path(file_path)
	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_text(code, encoding="utf-8")
	return f"Successfully wrote file: {target}"
