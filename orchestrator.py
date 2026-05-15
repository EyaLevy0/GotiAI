"""Main backend orchestrator for the Godot generation workflow.

This module builds a LangGraph state machine that wires together the team
roles A1-A4. A1 is a manager placeholder, A2 is the real Creator Agent,
A3 is the real Sprite Agent, and A4 is the Tester Agent.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from creator_agent.main import run_coder_agent
from sprite_agent.main import run_agent as run_sprite_agent
from tester_agent.main import run_agent as run_tester_agent


class WorkflowState(TypedDict, total=False):
	"""Shared workflow state passed between LangGraph nodes."""

	user_prompt: str
	game_design_doc: str
	selected_kit: str
	project_path: str
	assets_injected: bool
	code_saved: bool
	generated_code: str
	asset_instructions: str
	status: str
	compile_result: str
	fix_attempted: bool

def _default_project_path() -> str:
	"""Resolve a usable project path for the manager placeholder.

	The first real manager implementation should replace this logic with a
	proper project-selection strategy. For now we support an environment
	override and fall back to the current working directory.
	"""

	return os.getenv("GODOT_PROJECT_PATH", str(Path.cwd()))


def _default_selected_kit() -> str:
	"""Resolve a usable default kit for the sprite injector."""

	return os.getenv("GODOT_SELECTED_KIT", "platformer")


# TODO: Import actual functions from teammates
async def a1_manager(state: WorkflowState) -> WorkflowState:
	"""Placeholder manager node.

	Initializes the project path, selected kit, and game design summary.
	"""

	return {
		**state,
		"project_path": state.get("project_path") or _default_project_path(),
		"selected_kit": state.get("selected_kit") or _default_selected_kit(),
		"game_design_doc": state.get("game_design_doc") or state.get("user_prompt", ""),
		"status": "A1_manager_completed",
	}


# TODO: Import actual functions from teammates
async def a2_coder(state: WorkflowState) -> WorkflowState:
	"""Creator node that delegates to the real Creator Agent (A2).

	The coder agent consumes the design doc and asset instructions to generate
	Godot GDScript files.
	"""

	asset_instructions = state.get("asset_instructions") or (
		f"Use sprites from the {state.get('selected_kit', 'platformer')} kit in assets/."
	)
	updated_state = await run_coder_agent({
		**state,
		"game_design_doc": state.get("game_design_doc") or state.get("user_prompt", ""),
		"asset_instructions": asset_instructions,
	})
	return {
		**state,
		**updated_state,
		"code_saved": bool(updated_state.get("code_saved", False)),
		"status": updated_state.get("status", "A2_coder_completed"),
	}


async def a3b_import_assets(state: WorkflowState) -> WorkflowState:
	"""Run Godot once headlessly to import the freshly copied PNG/JPG assets.

	Godot 4 needs ``.import`` sidecar files before ``load("res://...")`` works.
	A short headless run with ``--import`` generates them.
	"""
	import subprocess
	from tester_agent.tools import _resolve_godot_executable

	project_path = state.get("project_path", "")
	exe = _resolve_godot_executable()
	try:
		subprocess.run(
			[exe, "--headless", "--import", "--path", project_path],
			capture_output=True,
			text=True,
			timeout=60,
		)
	except Exception as exc:
		print(f"Asset import warning: {exc}")
	return {**state, "status": "A3b_assets_imported"}


async def a3_sprite(state: WorkflowState) -> WorkflowState:
	"""Sprite node that delegates to the real Sprite Agent (A3).

	This agent injects the selected asset kit into the Godot project and
	returns an updated state that downstream nodes can consume.
	"""

	updated_state = await run_sprite_agent(state)
	return {
		**state,
		**updated_state,
		"assets_injected": bool(updated_state.get("assets_injected", False)),
		"status": updated_state.get("status", "A3_sprite_completed"),
	}


async def a4_tester(state: WorkflowState) -> WorkflowState:
	"""Tester node — compiles the project and captures any errors.

	Captures the compile result into ``state["compile_result"]`` so a
	downstream fix-up node can react to it.
	"""

	project_path = state["project_path"]
	from tester_agent.tools import run_godot_compiler
	compile_result = run_godot_compiler.invoke({"project_path": project_path})
	print("COMPILE_RESULT:", compile_result)
	return {
		**state,
		"compile_result": compile_result,
		"status": "A4_tester_completed",
	}


async def a2_fixer(state: WorkflowState) -> WorkflowState:
	"""If A4 reported errors, re-run A2 with the errors as feedback.

	Limited to a single fix attempt per pipeline run to keep cost bounded.
	"""
	compile_result = state.get("compile_result", "")
	if not compile_result or "GODOT_COMPILER_ERRORS" not in compile_result:
		return {**state, "status": "A2_fixer_skipped"}
	if state.get("fix_attempted"):
		return {**state, "status": "A2_fixer_skipped_already_attempted"}

	error_excerpt = compile_result[:2000]
	fix_doc = (
		f"{state.get('game_design_doc', '')}\n\n"
		"# FIX REQUIRED\n"
		"The previous pass produced GDScript that Godot failed to parse.\n"
		"Rewrite every file using the same architecture, but fix the errors below.\n"
		"Pay special attention to: undeclared identifiers, wrong type hints,\n"
		"and Godot-3 patterns. Do not introduce class_name cross-references.\n\n"
		"Godot compiler output:\n"
		f"```\n{error_excerpt}\n```\n"
	)
	updated_state = await run_coder_agent({
		**state,
		"game_design_doc": fix_doc,
		"asset_instructions": state.get("asset_instructions", ""),
	})
	return {
		**state,
		**updated_state,
		"fix_attempted": True,
		"status": "A2_fixer_completed",
	}


async def a4_tester_retest(state: WorkflowState) -> WorkflowState:
	"""Recompile after the fixer ran so the final status reflects the retry."""
	if state.get("status") == "A2_fixer_skipped":
		return state
	project_path = state["project_path"]
	from tester_agent.tools import run_godot_compiler
	compile_result = run_godot_compiler.invoke({"project_path": project_path})
	print("COMPILE_RESULT_AFTER_FIX:", compile_result)
	return {
		**state,
		"compile_result": compile_result,
		"status": "A4_tester_retested",
	}


def _build_graph() -> StateGraph[WorkflowState]:
	"""Create and wire the LangGraph workflow.

	START -> A1 -> A3 (sprites) -> A2 (code) -> A4 (test) -> A2_fix -> A4_retest -> END
	The A2_fix node is a no-op when A4 reports no errors.
	"""

	graph = StateGraph(WorkflowState)
	graph.add_node("A1", a1_manager)
	graph.add_node("A3", a3_sprite)
	graph.add_node("A3b", a3b_import_assets)
	graph.add_node("A2", a2_coder)
	graph.add_node("A4", a4_tester)
	graph.add_node("A2_fix", a2_fixer)
	graph.add_node("A4_retest", a4_tester_retest)

	graph.add_edge(START, "A1")
	graph.add_edge("A1", "A3")
	graph.add_edge("A3", "A3b")
	graph.add_edge("A3b", "A2")
	graph.add_edge("A2", "A4")
	graph.add_edge("A4", "A2_fix")
	graph.add_edge("A2_fix", "A4_retest")
	graph.add_edge("A4_retest", END)
	return graph


async def trigger_godot_generation(user_prompt: str) -> dict:
	"""Run the full orchestration graph for a user request.

	This entrypoint is designed for FastAPI / frontend routes. It compiles the
	graph, seeds the initial state with the user prompt, runs the workflow, and
	returns the final state dictionary.
	"""

	graph = _build_graph().compile()
	initial_state: WorkflowState = {"user_prompt": user_prompt}
	final_state = await graph.ainvoke(initial_state)
	return final_state

