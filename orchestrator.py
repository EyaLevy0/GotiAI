"""Main backend orchestrator for the Godot generation workflow.

This module builds a LangGraph state machine that wires together the team
roles A1-A4:
  A1 (manager)  – reads the contracts produced by the requirements_agent UI
  A2 (scene)    – calls the scene_agent to generate GDScript from the contract
  A3 (sprite)   – placeholder (sprite agent not yet implemented)
  A4 (tester)   – compiles the project and iteratively fixes errors
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from tester_agent.main import run_agent as run_tester_agent


# ---------------------------------------------------------------------------
# Shared workflow state
# ---------------------------------------------------------------------------

class WorkflowState(TypedDict, total=False):
	"""Shared workflow state passed between LangGraph nodes."""

	user_prompt: str
	project_path: str
	request_contract: dict
	sprite_contract: dict
	scene_output: str
	status: str


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_AGENT_DATA = Path(__file__).parent / "requirements_agent" / "agent_data"
_REQUEST_CONTRACT_PATH = _AGENT_DATA / "request_manager_contract.json"
_SPRITE_CONTRACT_PATH  = _AGENT_DATA / "sprite_generation_contract.json"


# ---------------------------------------------------------------------------
# A1 – Manager: read contracts written by the requirements_agent Streamlit app
# ---------------------------------------------------------------------------

async def a1_manager(state: WorkflowState) -> WorkflowState:
	"""Read the two JSON contracts produced by the requirements_agent UI.

	Raises FileNotFoundError with a clear message when the contracts are
	missing, so the user knows they must run the Streamlit app first.
	"""

	if not _REQUEST_CONTRACT_PATH.exists():
		raise FileNotFoundError(
			f"Request-manager contract not found at {_REQUEST_CONTRACT_PATH}. "
			"Run the requirements_agent Streamlit app and complete the conversation "
			"before launching the orchestrator."
		)

	request_contract: dict = json.loads(_REQUEST_CONTRACT_PATH.read_text(encoding="utf-8"))

	sprite_contract: dict = {}
	if _SPRITE_CONTRACT_PATH.exists():
		sprite_contract = json.loads(_SPRITE_CONTRACT_PATH.read_text(encoding="utf-8"))

	project_path: str = (
		state.get("project_path")
		or request_contract.get("project_directory_path", "")
	)

	return {
		**state,
		"project_path": project_path,
		"request_contract": request_contract,
		"sprite_contract": sprite_contract,
		"status": "A1_manager_completed",
	}


# ---------------------------------------------------------------------------
# A2 – Scene: generate GDScript via the scene_agent
# ---------------------------------------------------------------------------

def _build_scene_request(contract: dict) -> str:
	"""Convert a RequestManagerContract dict into a plain-English scene request."""

	mechanic   = contract.get("game_mechanic", "")
	enemies    = contract.get("enemy_interaction", "")
	abilities  = contract.get("character_abilities", [])
	start      = contract.get("start_screen_instructions", "")

	abilities_text = (
		", ".join(abilities) if isinstance(abilities, list) else str(abilities)
	)

	return (
		f"Game mechanic: {mechanic}\n"
		f"Enemy interaction: {enemies}\n"
		f"Character abilities: {abilities_text}\n"
		f"Start screen: {start}\n\n"
		"Generate the Godot scene nodes, GDScript files, and integration steps "
		"required to implement this game."
	)


async def a2_scene(state: WorkflowState) -> WorkflowState:
	"""Call the scene_agent to generate GDScript from the request contract.

	Imports are deferred so the orchestrator can be imported even if the
	scene_agent optional dependencies are not installed.
	"""

	from scene_agent.tools.godot_docs_tool import retrieve_godot_docs_context
	from scene_agent.main import SYSTEM_PROMPT, build_user_prompt
	from scene_agent.llm_client import ask_llm

	contract = state.get("request_contract", {})
	request_text = _build_scene_request(contract)

	docs = retrieve_godot_docs_context(request_text, max_pages=2, max_total_chars=6000)
	user_prompt = build_user_prompt(docs, request_text)

	scene_output = ask_llm(
		prompt=user_prompt,
		system_prompt=SYSTEM_PROMPT,
		temperature=0.2,
		max_tokens=2000,
	)

	return {
		**state,
		"scene_output": scene_output,
		"status": "A2_scene_completed",
	}


# ---------------------------------------------------------------------------
# A3 – Sprite: placeholder (sprite agent not yet implemented)
# ---------------------------------------------------------------------------

async def a3_sprite(state: WorkflowState) -> WorkflowState:
	"""Placeholder sprite node.

	TODO: implement once the sprite_agent module is available.
	The sprite_contract in state already contains the structured data needed.
	"""

	return {
		**state,
		"status": "A3_sprite_completed",
	}


# ---------------------------------------------------------------------------
# A4 – Tester: compile + fix loop
# ---------------------------------------------------------------------------

async def a4_tester(state: WorkflowState) -> WorkflowState:
	"""Delegate to the tester agent which runs a compile/search/fix ReAct loop."""

	project_path = state["project_path"]
	await run_tester_agent(project_path)
	return {
		**state,
		"status": "A4_tester_completed",
	}


# ---------------------------------------------------------------------------
# Graph wiring
# ---------------------------------------------------------------------------

def _build_graph() -> StateGraph:
	"""Create and wire the LangGraph workflow: START → A1 → A2 → A3 → A4 → END."""

	graph: StateGraph = StateGraph(WorkflowState)
	graph.add_node("A1", a1_manager)
	graph.add_node("A2", a2_scene)
	graph.add_node("A3", a3_sprite)
	graph.add_node("A4", a4_tester)

	graph.add_edge(START, "A1")
	graph.add_edge("A1", "A2")
	graph.add_edge("A2", "A3")
	graph.add_edge("A3", "A4")
	graph.add_edge("A4", END)
	return graph


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

async def trigger_godot_generation(user_prompt: str) -> dict:
	"""Run the full orchestration graph for a user request.

	Designed for FastAPI / frontend routes. Compiles the graph, seeds the
	initial state with the user prompt, runs the workflow, and returns the
	final state dictionary.
	"""

	graph = _build_graph().compile()
	initial_state: WorkflowState = {"user_prompt": user_prompt}
	final_state = await graph.ainvoke(initial_state)
	return final_state
