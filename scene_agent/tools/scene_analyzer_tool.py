"""
Scene Analyzer Tool.

This tool receives an approved RequestManagerContract and converts it into a
structured file generation plan for the Scene Creator pipeline.
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
            "Example: scenes/main.tscn or scripts/player_controller.gd."
        )
    )

    # Keeps the file type explicit so the code writer knows how to handle it.
    file_type: str = Field(
        description="The type of file to generate. Expected values: 'tscn' or 'gd'."
    )

    # Explains the responsibility of this file in the generated Godot project.
    purpose: str = Field(
        description="A short explanation of what this file is responsible for."
    )

    # Helps the documentation tool know which Godot APIs may be relevant.
    godot_nodes_or_classes: List[str] = Field(
        description="Relevant Godot nodes, classes, or APIs needed for this file."
    )


class SceneAnalysisResult(BaseModel):
    """
    Structured result returned by the Scene Analyzer.
    """

    # The concrete list of files that the next stage should generate.
    files_to_generate: List[FileGenerationPlan] = Field(
        description="List of Godot scene and script files that should be generated."
    )

    # Topics that should be checked by godot_docs_tool.py before code generation.
    docs_needed: List[str] = Field(
        description="Godot 4 documentation topics that should be checked before code generation."
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
    It only decides which files are needed and what each file should do.
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