"""Main backend orchestrator for the Godot generation workflow.

This module builds a LangGraph state machine that wires together the team
roles A1-A4. The current implementation keeps A1-A3 as placeholders and
integrates the working tester agent as A4.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from sprite_agent.main import run_agent as run_sprite_agent
from tester_agent.main import run_agent as run_tester_agent


class WorkflowState(TypedDict, total=False):
	"""Shared workflow state passed between LangGraph nodes."""

	user_prompt: str
	selected_kit: str
	project_path: str
	assets_injected: bool
	status: str
	asset_instructions: str

def _default_project_path() -> str:
	"""Resolve a usable project path for the manager placeholder.

	The first real manager implementation should replace this logic with a
	proper project-selection strategy. For now we support an environment
	override and fall back to the current working directory.
	"""

	return os.getenv("GODOT_PROJECT_PATH", str(Path.cwd()))


# TODO: Import actual functions from teammates
async def a1_manager(state: WorkflowState) -> WorkflowState:
	"""Placeholder manager node.

	Initializes the project path and marks the workflow as routed through A1.
	"""

	return {
		**state,
		"project_path": state.get("project_path") or _default_project_path(),
		"status": "A1_manager_completed",
	}


# TODO: Import actual functions from teammates
async def a2_scene(state: WorkflowState) -> WorkflowState:
	"""Placeholder scene node.

	This currently simulates scene orchestration work and preserves the
	project path for downstream nodes.
	"""

	return {
		**state,
		"status": "A2_scene_completed",
	}


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
	"""Tester node that delegates to the working tester agent.

	The tester agent performs the compile/search/read/write loop for the
	project path stored in the shared workflow state.
	"""

	project_path = state["project_path"]
	await run_tester_agent(project_path)
	return {
		**state,
		"status": "A4_tester_completed",
	}


def _build_graph() -> StateGraph[WorkflowState]:
	"""Create and wire the LangGraph workflow.

	The first version is sequential for clarity and reliability:
	START -> A1 -> A2 -> A3 -> A4 -> END
	"""

	graph = StateGraph(WorkflowState)
	graph.add_node("A1", a1_manager)
	graph.add_node("A2", a2_scene)
	graph.add_node("A3", a3_sprite)
	graph.add_node("A4", a4_tester)

	graph.add_edge(START, "A1")
	graph.add_edge("A1", "A3")
	graph.add_edge("A3", "A2")
	graph.add_edge("A2", "A4")
	graph.add_edge("A4", END)
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

