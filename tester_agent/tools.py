"""Utility helpers and LangChain tools for the Tester Agent."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from langchain_core.tools import tool
from duckduckgo_search import DDGS

DEFAULT_TIMEOUT_SECONDS = 120
ERROR_CONTEXT_RADIUS = 2
GODOT_EXECUTABLE_ENV_VARS = ("GODOT_EXECUTABLE", "GODOT_BIN", "GODOT_PATH")


@dataclass(slots=True)
class TesterAgentConfig:
	api_key: str = ""
	model: str = ""
	log_level: str = "INFO"
	agent_name: str = "Tester Agent"
	godot_executable: str = ""
	compiler_timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS


def load_config() -> TesterAgentConfig:
	"""Load agent configuration from environment variables."""
	timeout_value = os.getenv("GODOT_COMPILER_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))
	try:
		timeout_seconds = max(1, int(timeout_value))
	except ValueError:
		timeout_seconds = DEFAULT_TIMEOUT_SECONDS

	return TesterAgentConfig(
		api_key=os.getenv("API_KEY", ""),
		model=os.getenv("MODEL", ""),
		log_level=os.getenv("LOG_LEVEL", "INFO"),
		agent_name=os.getenv("TESTER_AGENT_NAME", "Tester Agent"),
		godot_executable=_resolve_godot_executable(),
		compiler_timeout_seconds=timeout_seconds,
	)


def is_configured(config: TesterAgentConfig) -> bool:
	"""Return whether the agent has the minimum configuration needed to run."""
	return bool(config.api_key and config.model)


def _resolve_godot_executable() -> str:
	for env_name in GODOT_EXECUTABLE_ENV_VARS:
		value = os.getenv(env_name, "").strip()
		if value:
			return value
	return "godot"


def _build_godot_command(executable: str, project_path: str) -> list[str]:
	return [executable, "--headless", "--path", project_path, "--quit"]


def _normalize_lines(text: str) -> list[str]:
	return [line.rstrip("\r") for line in text.splitlines()]


def _find_error_line_indexes(lines: list[str]) -> list[int]:
	indexes: list[int] = []
	for index, line in enumerate(lines):
		if re.search(r"\b(?:ERROR|Error)\b", line):
			indexes.append(index)
	return indexes


def _collect_context_lines(lines: list[str], match_indexes: Iterable[int], radius: int) -> list[str]:
	selected_indexes: set[int] = set()
	for index in match_indexes:
		start = max(0, index - radius)
		end = min(len(lines), index + radius + 1)
		selected_indexes.update(range(start, end))

	return [lines[index] for index in sorted(selected_indexes)]


def _extract_compiler_output(stdout: str, stderr: str, returncode: int) -> str:
	combined = "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)
	if not combined:
		return "SUCCESS" if returncode == 0 else f"Godot exited with code {returncode} and no output."

	lines = _normalize_lines(combined)
	error_indexes = _find_error_line_indexes(lines)

	if returncode == 0 and not error_indexes:
		return "SUCCESS"

	if error_indexes:
		context_lines = _collect_context_lines(lines, error_indexes, ERROR_CONTEXT_RADIUS)
		return "\n".join(["GODOT_COMPILER_ERRORS:", *context_lines])

	tail_lines = lines[-min(len(lines), 20):]
	return "\n".join([f"Godot exited with code {returncode}:", *tail_lines])


@tool("run_godot_compiler")
def run_godot_compiler(project_path: str) -> str:
	"""Run Godot in headless check-only mode and return parsed compiler output."""
	project_root = Path(project_path).expanduser()
	if not project_root.exists():
		return f"INVALID_PROJECT_PATH: {project_path} does not exist."
	if not (project_root / "project.godot").exists():
		return f"INVALID_PROJECT_PATH: No project.godot found in {project_path}."

	config = load_config()

	# Pre-step: ensure assets are imported (creates .godot/imported/*.ctex
	# sidecars so `load("res://assets/foo.png")` works at runtime).
	if not (project_root / ".godot" / "imported").exists():
		try:
			subprocess.run(
				[config.godot_executable, "--headless", "--path", str(project_root), "--import"],
				capture_output=True,
				text=True,
				timeout=120,
				check=False,
			)
		except Exception:
			pass

	command = _build_godot_command(config.godot_executable, str(project_root))

	try:
		completed_process = subprocess.run(
			command,
			capture_output=True,
			text=True,
			timeout=config.compiler_timeout_seconds,
			check=False,
			cwd=str(project_root),
		)
	except subprocess.TimeoutExpired as exc:
		stdout = (exc.stdout or "").strip()
		stderr = (exc.stderr or "").strip()
		captured = "\n".join(part for part in (stdout, stderr) if part)
		if captured:
			return "\n".join(
				[
					f"TIMEOUT: Godot compilation exceeded {config.compiler_timeout_seconds} seconds.",
					captured,
				]
			)
		return f"TIMEOUT: Godot compilation exceeded {config.compiler_timeout_seconds} seconds."
	except FileNotFoundError:
		return f"GODOT_EXECUTABLE_NOT_FOUND: could not run '{config.godot_executable}'."
	except OSError as exc:
		return f"GODOT_EXECUTION_FAILED: {exc}"

	return _extract_compiler_output(
		completed_process.stdout,
		completed_process.stderr,
		completed_process.returncode,
	)


@tool("search_godot_docs")
def search_godot_docs(error_message: str) -> str:
	"""Search Godot docs and community for fixes related to an error message.

	Uses `duckduckgo_search.ddg` to return a compact set of results.
	"""
	query = (
		f"Godot 4 GDScript error fix: {error_message} "
		"site:godotengine.org OR site:reddit.com/r/godot"
	)
	try:
		with DDGS() as ddgs:
			results = ddgs.text(query, max_results=6)
	except Exception as exc:  # pragma: no cover - environment-dependent
		return f"SEARCH_ERROR: {exc}"

	if not results:
		return "NO_SEARCH_RESULTS"

	entries = []
	for r in results:
		title = r.get("title") or r.get("text") or "(no title)"
		body = r.get("body") or r.get("snippet") or r.get("text") or ""
		href = r.get("href") or r.get("url") or ""
		entries.append(f"- {title}\n{body}\n{href}")

	return "SEARCH_RESULTS:\n" + "\n\n".join(entries)


@tool("read_file")
def read_file(file_path: str) -> str:
	"""Return the contents of a file (limited size) or an error message."""
	p = Path(file_path).expanduser()
	if not p.exists():
		return f"FILE_NOT_FOUND: {file_path}"
	try:
		size = p.stat().st_size
		if size > 200_000:
			return f"FILE_TOO_LARGE: {file_path} ({size} bytes)"
		return p.read_text(encoding="utf-8")
	except Exception as exc:
		return f"FILE_READ_ERROR: {exc}"


@tool("overwrite_file")
def overwrite_file(file_path: str, new_content: str) -> str:
	"""Overwrite `file_path` with `new_content`, returning a status string."""
	p = Path(file_path).expanduser()
	if not p.exists():
		return f"FILE_NOT_FOUND: {file_path}"
	try:
		# create a lightweight backup
		backup = p.with_suffix(p.suffix + ".bak")
		try:
			backup.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
		except Exception:
			# ignore backup failures
			pass

		p.write_text(new_content, encoding="utf-8")
		return f"OK: Overwrote {file_path}"
	except Exception as exc:
		return f"FILE_WRITE_ERROR: {exc}"

