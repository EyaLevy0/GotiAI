"""Async runner for the Creator Agent (A2)."""

from __future__ import annotations

import asyncio
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from creator_agent.prompts import SYSTEM_PROMPT
from creator_agent.tools import write_gdscript


def _render_system_prompt(game_design_doc: str, asset_instructions: str) -> str:
	return SYSTEM_PROMPT.format(
		game_design_doc=game_design_doc,
		asset_instructions=asset_instructions,
	)


async def run_coder_agent(state: dict) -> dict:
	project_path = state.get("project_path", "")
	game_design_doc = state.get("game_design_doc", state.get("user_prompt", ""))
	asset_instructions = state.get("asset_instructions", "")

	if not asset_instructions:
		selected_kit = state.get("selected_kit", "")
		if selected_kit:
			asset_instructions = f"Use sprites from the {selected_kit} kit in assets/."

	load_dotenv()
	llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)
	agent = create_react_agent(
		model=llm,
		tools=[write_gdscript],
		prompt=_render_system_prompt(game_design_doc, asset_instructions),
	)

	human_message = (
		f"Here is the game design: {game_design_doc}\n\n"
		f"Here are the asset instructions you MUST follow: {asset_instructions}\n\n"
		f"Project path: {project_path}\n\n"
		"Please generate the game code and save it using your tool."
	)

	try:
		result = await agent.ainvoke({"messages": [HumanMessage(content=human_message)]})
		output = result["messages"][-1].content
		return {
			**state,
			"code_saved": True,
			"generated_code": output,
			"status": "A2_coder_completed",
		}
	except Exception:
		import traceback

		traceback.print_exc()
		return {**state, "code_saved": False, "status": "A2_coder_failed"}
