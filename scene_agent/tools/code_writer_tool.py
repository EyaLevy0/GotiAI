"""
Code Writer Tool.

This tool generates the raw text content for a single Godot file, such as a
.gd script or a .tscn scene file, using the approved game contract, file plan,
dependency information, and relevant Godot documentation context.
"""

from pathlib import Path
from typing import List

from pydantic import BaseModel, Field

from scene_agent.llm_client import ask_llm
from scene_agent.models.scene_request import RequestManagerContract
from scene_agent.prompts import SCENE_CODE_WRITER_SYSTEM_PROMPT
from scene_agent.tools.file_manager_tool import FileManagerTool


class GeneratedFileContent(BaseModel):
    """
    Represents generated raw content for one Godot file.
    """

    # Relative path inside the Godot project.
    file_path: str = Field(
        description="Relative path where this file should be saved."
    )

    # The generated raw text content for the file.
    raw_content: str = Field(
        description="Exact raw file content that should be written to disk."
    )


class CodeWriterTool:
    """
    Generates raw Godot file content for one planned file at a time.
    """

    def build_file_prompt(
        self,
        contract: RequestManagerContract,
        file_path: str,
        file_type: str,
        file_purpose: str,
        docs_context: str,
        depends_on: List[str],
        existing_files: List[str],
    ) -> str:
        """
        Build the user prompt for generating one specific Godot file.
        """

        return f"""
Generate the exact raw content for one Godot 4 file.

Project directory path:
{contract.project_directory_path}

Game mechanic:
{contract.game_mechanic}

Enemy interaction:
{contract.enemy_interaction}

Start screen instructions:
{contract.start_screen_instructions}

Character abilities:
{contract.character_abilities}

Target file path:
{file_path}

Target file type:
{file_type}

Target file purpose:
{file_purpose}

Files this target file is allowed to depend on:
{depends_on}

Files that already exist in the project:
{existing_files}

Relevant Godot documentation context:
{docs_context}

Rules:
- Generate only the raw content for this single file.
- Do not include markdown.
- Do not include explanations.
- Do not wrap the result in code fences.
- Use valid Godot 4 syntax.
- For .gd files, use valid Godot 4 GDScript.
- For .tscn files, use valid Godot 4 text scene format.
- Keep the file focused on its stated purpose.
- Use res:// paths when referencing internal Godot project files.
- Only reference files listed in dependencies or files that already exist.
- Do not reference future files that have not been created yet.
"""

    def generate_file_content(
        self,
        contract: RequestManagerContract,
        file_path: str,
        file_type: str,
        file_purpose: str,
        docs_context: str,
        depends_on: List[str],
        existing_files: List[str],
    ) -> GeneratedFileContent:
        """
        Generate raw content for a single Godot file.
        """

        # Build a focused prompt for one file only.
        prompt = self.build_file_prompt(
            contract=contract,
            file_path=file_path,
            file_type=file_type,
            file_purpose=file_purpose,
            docs_context=docs_context,
            depends_on=depends_on,
            existing_files=existing_files,
        )

        # Ask the local LLM to generate the raw file content.
        raw_content = ask_llm(
            prompt=prompt,
            system_prompt=SCENE_CODE_WRITER_SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=900,
        )

        return GeneratedFileContent(
            file_path=file_path,
            raw_content=raw_content.strip(),
        )

    def generate_and_save_file(
        self,
        contract: RequestManagerContract,
        file_manager: FileManagerTool,
        file_path: str,
        file_type: str,
        file_purpose: str,
        docs_context: str,
        depends_on: List[str],
        existing_files: List[str],
    ) -> Path:
        """
        Generate raw content for one Godot file and save it inside the project.
        """

        # Generate the file content using the LLM.
        generated_file = self.generate_file_content(
            contract=contract,
            file_path=file_path,
            file_type=file_type,
            file_purpose=file_purpose,
            docs_context=docs_context,
            depends_on=depends_on,
            existing_files=existing_files,
        )

        # Save the generated content through the file manager.
        saved_path = file_manager.write_file(
            relative_file_path=generated_file.file_path,
            content=generated_file.raw_content,
        )

        return saved_path