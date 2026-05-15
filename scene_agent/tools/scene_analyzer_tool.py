"""
Scene Analyzer Tool.

This tool receives an approved RequestManagerContract and converts it into a
structured, dependency-aware file generation plan for the Scene Creator pipeline.
"""

from typing import List
from pydantic import BaseModel, Field
from langchain_core.output_parsers import PydanticOutputParser

from scene_agent.models.scene_request import RequestManagerContract
from scene_agent.prompts import SCENE_ANALYZER_PROMPT


class FileGenerationPlan(BaseModel):
    """
    Describes one Godot file that should be generated later by the code writer.
    """

    # Relative path inside the Godot project, not the full computer path.
    file_path: str = Field(
        description=(
            "Relative path of the file inside the Godot project. "
            "Example: scenes/player.tscn or scripts/player_controller.gd."
        )
    )

    # Keeps the file type explicit so the code writer knows how to handle it.
    file_type: str = Field(
        description="The type of file to generate. Expected values: 'tscn' or 'gd'."
    )

    # The game entity or system this file belongs to, such as Player, Enemy, or Level.
    entity_name: str = Field(
        description=(
            "The entity or system this file belongs to. "
            "Examples: Player, Enemy, Coin, StartScreen, Level."
        )
    )

    # Defines the bottom-up creation stage for this file.
    generation_stage: str = Field(
        description=(
            "The generation stage for dependency-safe creation. "
            "Expected values: 'atomic_asset', 'supporting_asset', or 'composite_scene'."
        )
    )

    # Other files that must exist before this file can safely reference them.
    depends_on: List[str] = Field(
        description=(
            "Relative file paths that must be generated before this file. "
            "Example: scenes/level.tscn may depend on scenes/player.tscn."
        )
    )

    # Explains the responsibility of this file in the generated Godot project.
    purpose: str = Field(
        description="A short explanation of what this file is responsible for."
    )

    # Helps the documentation tool know which Godot APIs may be relevant.
    godot_nodes_or_classes: List[str] = Field(
        description="Relevant Godot nodes, classes, or APIs needed for this file."
    )


class MCPActionPlan(BaseModel):
    """
    Describes one Godot MCP action that may be useful in a later pipeline stage.
    """

    # Name of the Godot MCP capability that should be used later.
    action_name: str = Field(
        description=(
            "Suggested Godot MCP action name. "
            "Examples: get_godot_version, analyze_project, create_scene, "
            "add_node, save_scene, run_project, capture_debug_output."
        )
    )

    # Explains why this MCP action is useful for the generated game.
    purpose: str = Field(
        description="Short explanation of why this MCP action may be needed."
    )

    # Target file, scene, node, or project path related to this action.
    target: str = Field(
        description=(
            "Relevant scene, script, project path, or node target for this MCP action."
        )
    )


class SceneAnalysisResult(BaseModel):
    """
    Structured result returned by the Scene Analyzer.
    """

    # The concrete list of files that the next stage should generate.
    files_to_generate: List[FileGenerationPlan] = Field(
        description=(
            "List of Godot scene and script files that should be generated, "
            "ordered from lowest-level dependencies to the main composite scene."
        )
    )

    # Topics that should be checked by godot_docs_tool.py before code generation.
    docs_needed: List[str] = Field(
        description="Godot 4 documentation topics that should be checked before code generation."
    )

    # Godot MCP actions that later agents can use for project inspection or validation.
    mcp_actions_needed: List[MCPActionPlan] = Field(
        description=(
            "Godot MCP actions that may be useful later for creating, inspecting, "
            "running, or debugging the generated Godot project."
        )
    )

    # Assumptions are used instead of asking the user, because validation happened earlier.
    implementation_assumptions: List[str] = Field(
        description=(
            "Reasonable assumptions needed because the contract does not include "
            "every small implementation detail."
        )
    )


class SceneAnalyzerTool:
    """
    Converts an approved game contract into a concrete Godot file generation plan.

    This tool does not write .gd or .tscn content.
    It only decides which files are needed, what each file should do, and in
    which dependency-safe order the files should be generated.
    """

    def __init__(self, llm):
        # The LLM is injected from outside so this tool can work with any provider.
        self.llm = llm

        # The parser forces the model output into the SceneAnalysisResult structure.
        self.parser = PydanticOutputParser(pydantic_object=SceneAnalysisResult)

    def analyze(self, contract: RequestManagerContract) -> SceneAnalysisResult:
        """
        Analyze the approved contract and return a structured file generation plan.
        """

        # Build a LangChain pipeline: prompt -> LLM -> structured parser.
        chain = SCENE_ANALYZER_PROMPT | self.llm | self.parser

        return chain.invoke(
            {
                "project_directory_path": contract.project_directory_path,
                "game_mechanic": contract.game_mechanic,
                "enemy_interaction": contract.enemy_interaction,
                "start_screen_instructions": contract.start_screen_instructions,
                "character_abilities": contract.character_abilities,
                "format_instructions": self.parser.get_format_instructions(),
            }
        )
