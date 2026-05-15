"""Scene Generation Agent - Agentic Implementation."""

import os
from typing import Any
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from scene_agent.tools.code_writer_tool import code_writer_tool
from scene_agent.tools.file_manager_tool import file_manager_tool

SYSTEM_PROMPT = """You are a Godot 4 Senior Developer. 
Your goal is to build a playable 2D game scene based on the provided contract.

You MUST:
1. Create a 'project.godot' file if it doesn't exist.
2. Write 'main.gd' and any necessary '.tscn' files.
3. Ensure all paths use 'res://'.
4. Use the provided Kits assets if mentioned in the context.

Use the code_writer_tool to save your work to the disk."""

async def run_scene_generation_agent(project_path: str, contract: dict) -> str:
    """
    Initializes and runs a ReAct agent to create the Godot project files.
    """
    llm = ChatOpenAI(
        model="openai/gpt-4o-mini", # Reliable for tool calling
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
        temperature=0
    )

    tools = [code_writer_tool, file_manager_tool]
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "Project Path: {project_path}\nGame Contract: {contract}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_openai_functions_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

    result = await executor.ainvoke({
        "project_path": project_path,
        "contract": str(contract)
    })
    
    return result["output"]
"""
Prompt templates for the Scene Creator pipeline.

This file keeps the LLM instructions short and focused so the pipeline can use
them without wasting unnecessary context.
"""

from langchain_core.prompts import ChatPromptTemplate


# System prompt for the Scene Analyzer step.
# This step creates a file generation plan, not the final code.
SCENE_ANALYZER_SYSTEM_PROMPT = """
You are the Scene Analyzer in a local autonomous pipeline that generates Godot 4 games.

You receive an approved RequestManagerContract from the Request Manager.
Do not ask the user questions.
Do not write final .gd or .tscn raw file content.
Do not generate sprites.

Your job is to break the contract into a concrete file generation plan.

Return only structured data describing:
- which Godot files should be generated
- the purpose of each file
- which Godot nodes, classes, or APIs are needed
- which Godot documentation topics should be checked
- implementation assumptions needed for missing details

Prefer small focused files, clean responsibilities, object-oriented design, and Godot 4 conventions.
"""


# Prompt used by scene_analyzer_tool.py.
SCENE_ANALYZER_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SCENE_ANALYZER_SYSTEM_PROMPT),
        (
            "human",
            """
Analyze this approved game contract:

Project directory path:
{project_directory_path}

Game mechanic:
{game_mechanic}

Enemy interaction:
{enemy_interaction}

Start screen instructions:
{start_screen_instructions}

Character abilities:
{character_abilities}

Use this exact output format:
{format_instructions}
"""
        ),
    ]
)


# System prompt for the later code generation step.
# This is not used by the analyzer directly, but it belongs here for the code writer.
SCENE_CODE_WRITER_SYSTEM_PROMPT = """
You are the Scene Code Writer in a local autonomous pipeline that generates Godot 4 games.

You receive:
- an approved RequestManagerContract
- a file generation plan
- relevant Godot 4 documentation context

Your job is to generate exact raw text content for Godot 4 .tscn and .gd files.

Rules:
- Generate valid Godot 4 syntax.
- Use Godot 4 GDScript only.
- Output raw file content only when asked for a specific file.
- Keep each file focused on one responsibility.
- Use clean object-oriented structure where appropriate.
- Do not ask the user questions.
- Do not generate sprites.
- Do not return high-level explanations instead of code.
- Use concise practical comments inside code when useful.
"""