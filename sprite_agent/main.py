"""Async runner for the Sprite Agent (A3)."""

from __future__ import annotations

from sprite_agent.tools import inject_kit_assets


async def run_agent(state: dict) -> dict:
    """Run the Sprite Agent against the provided workflow state.

    Expected state keys:
    - `selected_kit`
    - `project_path`
    """

    selected_kit = state.get("selected_kit")
    project_path = state.get("project_path")

    if not selected_kit or not project_path:
        return {
            **state,
            "assets_injected": False,
            "status": "A3_sprite_missing_input",
            "error": "Missing selected_kit or project_path in state.",
        }

    # This agent is intentionally deterministic: it only needs to copy the
    # selected kit and generate the helper GDScript, so no LLM is required.
    result = inject_kit_assets.invoke(
        {
            "selected_kit": selected_kit,
            "godot_project_path": project_path,
        }
    )

    assets_injected = isinstance(result, str) and result.startswith("Success:")

    return {
        **state,
        "assets_injected": assets_injected,
        "status": "A3_sprite_completed",
        "sprite_agent_result": result,
    }
