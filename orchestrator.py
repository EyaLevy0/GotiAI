"""Main backend orchestrator for the Godot generation workflow.

Refactored to support direct state injection and agentic file creation.
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
    selected_kit: str
    game_design_doc: str
    request_contract: dict
    sprite_contract: dict
    assets_injected: bool
    asset_instructions: str
    code_saved: bool
    generated_code: str
    scene_output: str
    tester_completed: bool
    status: str

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_AGENT_DATA = Path(__file__).parent / "requirements_agent" / "agent_data"
_REQUEST_CONTRACT_PATH = _AGENT_DATA / "request_manager_contract.json"
_SPRITE_CONTRACT_PATH  = _AGENT_DATA / "sprite_generation_contract.json"

# ---------------------------------------------------------------------------
# A1 – Manager: Consolidate data from memory or files
# ---------------------------------------------------------------------------

async def a1_manager(state: WorkflowState) -> WorkflowState:
    """
    Run the real A1 Planner agent from the `requirements_agent` package when
    available. The agent should accept a user prompt and return a dict that
    includes at least `game_design_doc` and `selected_kit`.

    If the explicit A1 entrypoint is not available, fall back to reading the
    saved contract JSON files and synthesizing a minimal `game_design_doc` and
    `selected_kit` so downstream agents can proceed.
    """
    user_prompt = state.get("user_prompt", "")

    # Try to call an explicit A1 entrypoint if it exists in requirements_agent
    try:
        import importlib
        req_pkg = importlib.import_module("requirements_agent")

        # Common candidate function names we might find — call the first that exists
        for fn_name in ("run_a1", "run_manager", "run_requirements_agent", "run_planner"):
            fn = getattr(req_pkg, fn_name, None)
            if fn:
                maybe = fn(user_prompt) if not callable(fn.__call__) else fn(user_prompt)
                # If coroutine, await it
                if hasattr(maybe, "__await__"):
                    result = await maybe
                else:
                    result = maybe

                game_design_doc = result.get("game_design_doc") if isinstance(result, dict) else None
                selected_kit = result.get("selected_kit") if isinstance(result, dict) else None
                if game_design_doc or selected_kit:
                    return {
                        **state,
                        "game_design_doc": game_design_doc or "",
                        "selected_kit": selected_kit or "platformer",
                        "status": "A1_manager_completed",
                    }
    except Exception:
        # Best-effort — we'll fallback below
        pass

    # Fallback: read saved contracts written by the requirements_agent tools
    request_contract = state.get("request_contract")
    sprite_contract = state.get("sprite_contract")

    if not request_contract and _REQUEST_CONTRACT_PATH.exists():
        request_contract = json.loads(_REQUEST_CONTRACT_PATH.read_text(encoding="utf-8"))

    if not sprite_contract and _SPRITE_CONTRACT_PATH.exists():
        sprite_contract = json.loads(_SPRITE_CONTRACT_PATH.read_text(encoding="utf-8"))

    project_path = state.get("project_path") or (request_contract or {}).get("project_directory_path")

    # Synthesize a simple design doc if none is present
    if request_contract:
        game_design_doc = (
            f"Design summary based on request contract: {json.dumps(request_contract, ensure_ascii=False)}"
        )
    else:
        game_design_doc = user_prompt or ""

    selected_kit = (sprite_contract or {}).get("main_character") or "platformer"

    return {
        **state,
        "project_path": project_path,
        "request_contract": request_contract,
        "sprite_contract": sprite_contract,
        "game_design_doc": game_design_doc,
        "selected_kit": selected_kit,
        "status": "A1_manager_completed",
    }

# ---------------------------------------------------------------------------
# A2 – Scene: Agentic file generation
# ---------------------------------------------------------------------------

async def a2_scene(state: WorkflowState) -> WorkflowState:
    """
    Triggers the SceneAgent to generate and write GDScript/TSCN files.
    """
    from scene_agent.main import run_scene_generation_agent
    
    project_path = state["project_path"]
    contract = state["request_contract"]
    
    # The agent now handles physical file writing using tools
    result = await run_scene_generation_agent(project_path, contract)
    
    return {
        **state,
        "scene_output": result,
        "status": "A2_scene_completed",
    }

# ---------------------------------------------------------------------------
# A3 – Sprite: Placeholder
# ---------------------------------------------------------------------------

async def a3_sprite(state: WorkflowState) -> WorkflowState:
    return {
        **state,
        "status": "A3_sprite_completed",
    }

# ---------------------------------------------------------------------------
# A4 – Tester: compile + fix loop
# ---------------------------------------------------------------------------

async def a4_tester(state: WorkflowState) -> WorkflowState:
    project_path = state["project_path"]
    await run_tester_agent(project_path)
    return {
        **state,
        "tester_completed": True,
        "status": "A4_tester_completed",
    }

# ---------------------------------------------------------------------------
# Graph wiring
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
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


async def trigger_godot_generation(user_prompt: str, initial_contracts: dict = None) -> dict:
    """Entry point for the workflow. Supports injecting contracts directly."""
    graph = build_graph().compile()

    initial_state: WorkflowState = {"user_prompt": user_prompt}
    if initial_contracts:
        initial_state.update(initial_contracts)

    final_state = await graph.ainvoke(initial_state)
    return final_state

