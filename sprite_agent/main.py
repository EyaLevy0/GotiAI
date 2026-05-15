"""Async runner for the Sprite Agent (A3)."""

from __future__ import annotations

import asyncio
from typing import Any

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from sprite_agent.prompts import SYSTEM_PROMPT
from sprite_agent.tools import inject_kit_assets


def _build_agent() -> Any:
    """Construct a tool-calling agent bound to the sprite asset tool."""

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    return create_agent(model=llm, tools=[inject_kit_assets], system_prompt=SYSTEM_PROMPT)


async def run_agent(state: dict) -> dict:
    """Run the Sprite Agent against the provided workflow state.

    Expected state keys:
    - `selected_kit`
    - `project_path`
    """

    load_dotenv()

    selected_kit = state.get("selected_kit")
    project_path = state.get("project_path")

    if not selected_kit or not project_path:
        return {
            **state,
            "assets_injected": False,
            "status": "A3_sprite_missing_input",
            "error": "Missing selected_kit or project_path in state.",
        }

    agent = _build_agent()
    instruction = (
        "Use the inject_kit_assets tool exactly once with the provided state. "
        "Manage assets only. Do not write gameplay code.\n\n"
        f"selected_kit: {selected_kit}\n"
        f"project_path: {project_path}"
    )

    payload = {"messages": [{"role": "user", "content": instruction}]}
    if hasattr(agent, "ainvoke"):
        result = await agent.ainvoke(payload)
    else:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, agent.invoke, payload)

    return {
        **state,
        "assets_injected": True,
        "status": "A3_sprite_completed",
        "sprite_agent_result": result,
    }
