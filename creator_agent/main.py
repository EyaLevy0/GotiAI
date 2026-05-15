"""Async runner for the Creator Agent (A2)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from creator_agent.prompts import SYSTEM_PROMPT
from creator_agent.tools import write_gdscript


def _render_system_prompt(game_design_doc: str, asset_instructions: str) -> str:
	return SYSTEM_PROMPT.format(
		game_design_doc=game_design_doc,
		asset_instructions=asset_instructions,
	)


def _validate_playable_level(project_path: str) -> tuple[list[str], list[str]]:
	"""Return (missing_files, wiring_issues) for a minimal playable level baseline.

	Baseline requested by user:
	- Start screen is optional
	- Must have a playable level with at least player + enemy logic files
	"""
	project_root = Path(project_path)
	required_files = [
		"main.gd",
		"level.gd",
		"player.gd",
		"enemy.gd",
	]
	missing_files = [name for name in required_files if not (project_root / name).exists()]

	wiring_issues: list[str] = []
	main_path = project_root / "main.gd"
	if main_path.exists():
		main_text = main_path.read_text(encoding="utf-8", errors="ignore").lower()
		# We require signs that main wires/instantiates level gameplay.
		if "level" not in main_text:
			wiring_issues.append("main.gd does not appear to instantiate or reference Level.")
		if "add_child" not in main_text:
			wiring_issues.append("main.gd does not appear to add gameplay nodes to the scene tree.")
	else:
		wiring_issues.append("main.gd missing, cannot verify gameplay wiring.")

	# Enforce concrete movement/physics behavior in player.gd.
	player_path = project_root / "player.gd"
	if player_path.exists():
		player_text = player_path.read_text(encoding="utf-8", errors="ignore").lower()
		if "extends characterbody2d" not in player_text:
			wiring_issues.append("player.gd must extend CharacterBody2D.")
		if "_physics_process" not in player_text:
			wiring_issues.append("player.gd must implement _physics_process for movement/physics.")
		if "velocity" not in player_text:
			wiring_issues.append("player.gd must use velocity for movement physics.")
		if "move_and_slide" not in player_text:
			wiring_issues.append("player.gd must call move_and_slide().")

	# Enforce enemy behavior presence.
	enemy_path = project_root / "enemy.gd"
	if enemy_path.exists():
		enemy_text = enemy_path.read_text(encoding="utf-8", errors="ignore").lower()
		has_enemy_behavior = any(
			marker in enemy_text
			for marker in ["_physics_process", "move_and_slide", "body_entered", "area_entered"]
		)
		if not has_enemy_behavior:
			wiring_issues.append(
				"enemy.gd must include movement or collision behavior (physics process or overlap signal)."
			)

	# Enforce level wiring to player and enemy nodes.
	level_path = project_root / "level.gd"
	if level_path.exists():
		level_text = level_path.read_text(encoding="utf-8", errors="ignore").lower()
		if "player" not in level_text:
			wiring_issues.append("level.gd must create/reference a Player node.")
		if "enemy" not in level_text:
			wiring_issues.append("level.gd must create/reference at least one Enemy node.")
		if "add_child" not in level_text:
			wiring_issues.append("level.gd must add gameplay nodes to the scene tree via add_child().")

	return missing_files, wiring_issues


async def run_coder_agent(state: dict) -> dict:
	project_path = state.get("project_path", "")
	game_design_doc = state.get("game_design_doc", state.get("user_prompt", ""))
	asset_instructions = state.get("asset_instructions", "")
	max_attempts = 3

	if not project_path:
		return {
			**state,
			"code_saved": False,
			"status": "A2_coder_missing_project_path",
			"error": "Missing project_path in state.",
		}

	if not asset_instructions:
		selected_kit = state.get("selected_kit", "")
		if selected_kit:
			asset_instructions = f"Use sprites from the {selected_kit} kit in assets/."

	load_dotenv()
	# Ensure write_gdscript can resolve `res://` paths into the real project root.
	os.environ["GODOT_PROJECT_PATH"] = project_path
	# If you have an OpenRouter API key, set OPENAI_API_KEY to that key and
	# OPENAI_API_BASE to https://api.openrouter.ai/v1 in your .env. Then
	# use ChatOpenAI which will send requests through the OpenRouter endpoint.
	llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
	agent = create_react_agent(
		model=llm,
		tools=[write_gdscript],
		prompt=_render_system_prompt(game_design_doc, asset_instructions),
	)

	base_human_message = (
		f"Here is the game design: {game_design_doc}\n\n"
		f"Here are the asset instructions you MUST follow: {asset_instructions}\n\n"
		f"Project path: {project_path}\n\n"
		"Please generate the game code and save it using your tool.\n"
		"Minimum acceptance: a playable level is required.\n"
		"You may waive the start screen if needed, but you MUST ensure main.gd "
		"instantiates/loads Level and the game includes Player + Enemy gameplay."
	)

	try:
		latest_output = ""
		feedback_suffix = ""
		for attempt in range(1, max_attempts + 1):
			human_message = base_human_message
			if feedback_suffix:
				human_message += "\n\n" + feedback_suffix

			result = await agent.ainvoke({"messages": [HumanMessage(content=human_message)]})
			latest_output = result["messages"][-1].content

			missing_files, wiring_issues = _validate_playable_level(project_path)
			if not missing_files and not wiring_issues:
				return {
					**state,
					"code_saved": True,
					"generated_code": latest_output,
					"status": "A2_coder_completed",
				}

			feedback_lines = [
				f"Guardrail retry {attempt}/{max_attempts}: output is incomplete.",
				"Regenerate missing parts and write them via write_gdscript now.",
				"You MUST update main.gd so gameplay Level is instantiated and playable.",
			]
			if missing_files:
				feedback_lines.append(f"Missing files: {missing_files}")
			if wiring_issues:
				feedback_lines.append(f"Wiring issues: {wiring_issues}")
			feedback_lines.append(
				"Start screen is optional. Playable level with player + enemy is mandatory."
			)
			feedback_suffix = "\n".join(feedback_lines)

		missing_files, wiring_issues = _validate_playable_level(project_path)
		return {
			**state,
			"code_saved": False,
			"status": "A2_coder_incomplete_output",
			"generated_code": latest_output,
			"missing_files": missing_files,
			"wiring_issues": wiring_issues,
			"error": "Creator agent did not reach the minimal playable-level baseline.",
		}
	except Exception:
		import traceback

		traceback.print_exc()
		return {**state, "code_saved": False, "status": "A2_coder_failed"}
