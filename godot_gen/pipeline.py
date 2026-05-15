"""Top-level pipeline. Bypasses godot_docs_tool.py entirely.

Flow:
  RequestManagerContract
    → SceneAnalyzerTool.plan(...)         (LLM #1)
    → CodeWriterTool.write(...) per file  (LLM #2 only for .gd)
    → FileManagerTool.write(...)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from code_writer_tool import CodeWriterTool
from contracts import FileGenerationPlan, FilePlanList, RequestManagerContract
from file_manager_tool import FileManagerTool
from llm_client import LLMClient
from scene_analyzer_tool import SceneAnalyzerTool


@dataclass
class PipelineResult:
    plan: FilePlanList
    written_paths: List[Path]


class Pipeline:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()
        self.analyzer = SceneAnalyzerTool(self.llm)
        self.writer = CodeWriterTool(self.llm)

    def run(self, contract: RequestManagerContract) -> PipelineResult:
        fm = FileManagerTool(contract.project_directory_path)

        # Step 1: plan
        plan = self.analyzer.plan(contract)

        # Step 2: write each file in dependency order
        written_paths: List[Path] = []
        summaries: List[str] = []
        for item in plan.files:
            content = self.writer.write(
                contract=contract,
                plan=item,
                all_plans=plan.files,
                written_files_summary=summaries,
            )
            path = fm.write(item.path, content)
            written_paths.append(path)
            summaries.append(f"{item.path} ({item.kind.value}): {item.purpose}")

        return PipelineResult(plan=plan, written_paths=written_paths)
