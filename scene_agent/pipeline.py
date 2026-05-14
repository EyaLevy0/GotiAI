"""
Scene Creator Pipeline.

This module connects the Scene Agent tools into one dependency-aware workflow:
analyze the approved contract, retrieve Godot documentation, generate file
content, and save the generated files into the local Godot project folder.
"""

from pathlib import Path
from typing import List, Optional

from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, Field

from scene_agent.llm_client import ask_llm
from scene_agent.models.scene_request import RequestManagerContract
from scene_agent.tools.code_writer_tool import CodeWriterTool
from scene_agent.tools.file_manager_tool import FileManagerTool
from scene_agent.tools.godot_docs_tool import retrieve_godot_docs_context
from scene_agent.tools.scene_analyzer_tool import (
    FileGenerationPlan,
    SceneAnalysisResult,
    SceneAnalyzerTool,
)


class GeneratedProjectFile(BaseModel):
    """
    Represents one file that was generated and saved by the pipeline.
    """

    # Relative path inside the Godot project.
    file_path: str = Field(
        description="Relative path of the generated file inside the Godot project."
    )

    # Absolute path on the local disk after saving.
    saved_path: str = Field(
        description="Absolute path where the file was saved on disk."
    )


class ScenePipelineResult(BaseModel):
    """
    Final result returned by the Scene Creator pipeline.
    """

    # Indicates whether the pipeline finished successfully.
    status: str = Field(
        description="Pipeline result status, for example: success."
    )

    # Structured analysis created by the SceneAnalyzerTool.
    analysis: SceneAnalysisResult = Field(
        description="The file generation plan created from the approved contract."
    )

    # Files that were generated and saved to disk.
    generated_files: List[GeneratedProjectFile] = Field(
        description="List of generated files saved inside the Godot project."
    )


def _create_default_analyzer_llm():
    """
    Create a LangChain-compatible wrapper around the local LLM client.

    SceneAnalyzerTool expects a LangChain runnable, so this wrapper converts the
    prompt object into text and sends it to the local LLM through ask_llm().
    """

    def call_local_llm(prompt_value):
        # ChatPromptTemplate outputs a prompt object, so we convert it to text.
        prompt_text = prompt_value.to_string()

        return ask_llm(
            prompt=prompt_text,
            temperature=0.2,
            max_tokens=800,
        )

    return RunnableLambda(call_local_llm)


def _build_docs_query(
    file_plan: FileGenerationPlan,
    global_docs_topics: List[str],
) -> str:
    """
    Build a compact documentation query for one planned file.
    """

    # Combine file-specific Godot APIs with global topics from the analyzer.
    topics = list(file_plan.godot_nodes_or_classes) + list(global_docs_topics)

    # Remove duplicates while preserving order.
    unique_topics = list(dict.fromkeys(topics))

    return " ".join(unique_topics)


def _validate_dependencies_ready(
    file_plan: FileGenerationPlan,
    existing_files: List[str],
) -> None:
    """
    Ensure all dependencies for a planned file already exist.

    This protects the bottom-up generation order by preventing a composite scene
    from referencing child scenes or scripts that have not been created yet.
    """

    missing_dependencies = [
        dependency
        for dependency in file_plan.depends_on
        if dependency not in existing_files
    ]

    if missing_dependencies:
        raise RuntimeError(
            "Cannot generate file before its dependencies exist. "
            f"File: {file_plan.file_path}. "
            f"Missing dependencies: {missing_dependencies}"
        )


def run_scene_creator_pipeline(
    contract: RequestManagerContract,
    analyzer_llm: Optional[object] = None,
) -> ScenePipelineResult:
    """
    Run the full Scene Creator pipeline for an approved game contract.

    This function analyzes the contract, retrieves documentation context for
    each planned file, generates raw file content, and saves the files to disk
    in a dependency-safe bottom-up order.
    """

    # Use a provided LLM for tests, or create a local LLM wrapper by default.
    llm = analyzer_llm if analyzer_llm is not None else _create_default_analyzer_llm()

    # Step 1: analyze the contract and decide which files are needed.
    analyzer = SceneAnalyzerTool(llm)
    analysis = analyzer.analyze(contract)

    # Step 2: prepare tools that will generate and save the files.
    code_writer = CodeWriterTool()
    file_manager = FileManagerTool(contract.project_directory_path)

    generated_files: List[GeneratedProjectFile] = []

    # Start from the files that already exist in the project folder.
    existing_files = file_manager.list_files()

    # Step 3: generate and save each planned Godot file in analyzer order.
    for file_plan in analysis.files_to_generate:
        # Make sure this file does not reference files that are not ready yet.
        _validate_dependencies_ready(
            file_plan=file_plan,
            existing_files=existing_files,
        )

        docs_query = _build_docs_query(
            file_plan=file_plan,
            global_docs_topics=analysis.docs_needed,
        )

        # Retrieve documentation context for this specific file.
        docs_context = retrieve_godot_docs_context(
            query=docs_query,
            max_pages=2,
            max_total_chars=5000,
        )

        # Generate the file content and save it inside the Godot project.
        saved_path: Path = code_writer.generate_and_save_file(
            contract=contract,
            file_manager=file_manager,
            file_path=file_plan.file_path,
            file_type=file_plan.file_type,
            file_purpose=file_plan.purpose,
            docs_context=docs_context,
            depends_on=file_plan.depends_on,
            existing_files=existing_files,
        )

        generated_files.append(
            GeneratedProjectFile(
                file_path=file_plan.file_path,
                saved_path=str(saved_path),
            )
        )

        # Update the known files list after saving this file.
        existing_files = file_manager.list_files()

    return ScenePipelineResult(
        status="success",
        analysis=analysis,
        generated_files=generated_files,
    )