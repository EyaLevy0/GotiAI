"""CodeWriterTool — produces the raw content of one file at a time.

Strategy:
- project.godot → deterministic template
- .tscn         → deterministic template (player/enemy/main)
- .tres         → deterministic placeholder
- .gd           → LLM
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from contracts import (
    FileGenerationPlan,
    FileKind,
    RequestManagerContract,
)
from godot_context import (
    CANONICAL_PATHS,
    render_enemy_scene,
    render_main_scene,
    render_player_scene,
    render_project_godot,
    render_sprite_frames_placeholder,
)
from llm_client import LLMClient
from prompts import CODE_WRITER_SYSTEM, code_writer_user_prompt
from settings import SETTINGS


class CodeWriterTool:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def write(
        self,
        contract: RequestManagerContract,
        plan: FileGenerationPlan,
        all_plans: List[FileGenerationPlan],
        written_files_summary: List[str],
    ) -> str:
        if plan.kind == FileKind.PROJECT_GODOT:
            project_name = Path(contract.project_directory_path).name or "GeneratedGame"
            return render_project_godot(project_name)

        if plan.kind == FileKind.RESOURCE:
            # Only player sprite frames for MVP; extend later if planner adds more.
            return render_sprite_frames_placeholder(plan.path)

        if plan.kind == FileKind.SCENE:
            return self._render_scene(plan, all_plans)

        if plan.kind == FileKind.GD_SCRIPT:
            return self._strip_artifacts(
                self.llm.chat(
                    system=CODE_WRITER_SYSTEM,
                    user=code_writer_user_prompt(
                        contract, plan, all_plans, written_files_summary
                    ),
                    model=SETTINGS.code_model,
                    max_tokens=SETTINGS.code_max_tokens,
                )
            )

        # OTHER — fall back to LLM but still strip fences.
        return self._strip_artifacts(
            self.llm.chat(
                system=CODE_WRITER_SYSTEM,
                user=code_writer_user_prompt(
                    contract, plan, all_plans, written_files_summary
                ),
                model=SETTINGS.code_model,
                max_tokens=SETTINGS.code_max_tokens,
            )
        )

    # -------- helpers --------

    def _render_scene(
        self, plan: FileGenerationPlan, all_plans: List[FileGenerationPlan]
    ) -> str:
        template = plan.deterministic_template

        def res_path(rel: str | None) -> str | None:
            return f"res://{rel}" if rel else None

        if template == "player_scene":
            return render_player_scene(res_path(plan.attach_script_to_scene))

        if template == "enemy_scene":
            return render_enemy_scene(res_path(plan.attach_script_to_scene))

        if template == "main_scene":
            # Find player scene in deps.
            player_scene = next(
                (p for p in plan.depends_on if p.endswith("Player.tscn")), None
            )
            return render_main_scene(
                main_script_res_path=res_path(plan.attach_script_to_scene),
                player_scene_res_path=res_path(player_scene),
            )

        # No deterministic template — generate minimal Node2D scene rather than
        # letting the LLM invent .tscn.
        return self._fallback_scene(plan)

    def _fallback_scene(self, plan: FileGenerationPlan) -> str:
        script_res = (
            f'[ext_resource type="Script" path="res://{plan.attach_script_to_scene}" id="s"]\n\n'
            if plan.attach_script_to_scene
            else ""
        )
        script_attr = (
            '\nscript = ExtResource("s")' if plan.attach_script_to_scene else ""
        )
        load_steps = 2 if plan.attach_script_to_scene else 1
        # Derive root name from path stem.
        root_name = Path(plan.path).stem
        return (
            f"[gd_scene load_steps={load_steps} format=3]\n\n"
            f"{script_res}"
            f'[node name="{root_name}" type="Node2D"]{script_attr}\n'
        )

    @staticmethod
    def _strip_artifacts(text: str) -> str:
        t = text.strip()
        # Strip a leading ```gdscript / ``` fence if the model added one.
        if t.startswith("```"):
            t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t.rsplit("```", 1)[0]
        return t.strip() + "\n"
