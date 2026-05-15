"""SceneAnalyzerTool — decides what files exist, in what order.

Hybrid approach: we let the LLM produce a plan, but we then enforce a
canonical baseline (player + main + project.godot are always present and
correctly wired) and dependency-safe ordering. This keeps the system robust
even when the local model misbehaves.
"""

from __future__ import annotations

import json
import re
from typing import List

from contracts import (
    FileGenerationPlan,
    FileKind,
    FilePlanList,
    RequestManagerContract,
)
from godot_context import CANONICAL_PATHS
from llm_client import LLMClient
from prompts import SCENE_ANALYZER_SYSTEM, scene_analyzer_user_prompt
from settings import SETTINGS


class SceneAnalyzerTool:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    # -------- public --------

    def plan(self, contract: RequestManagerContract) -> FilePlanList:
        raw = self.llm.chat(
            system=SCENE_ANALYZER_SYSTEM,
            user=scene_analyzer_user_prompt(contract),
            model=SETTINGS.analyzer_model,
            max_tokens=SETTINGS.analyzer_max_tokens,
            json_mode=True,
        )

        plan = self._parse(raw)
        plan = self._enforce_canonical(plan, contract)
        plan = self._dependency_order(plan)
        return plan

    # -------- internals --------

    def _parse(self, raw: str) -> FilePlanList:
        # Strip code fences if a model added them anyway.
        cleaned = re.sub(
            r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw.strip(), flags=re.MULTILINE
        )
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Fallback: pull the first {...} block.
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not match:
                return FilePlanList(files=[])
            data = json.loads(match.group(0))
        # Tolerate the analyzer returning a bare list.
        if isinstance(data, list):
            data = {"files": data}
        return FilePlanList.model_validate(data)

    def _enforce_canonical(
        self, plan: FilePlanList, contract: RequestManagerContract
    ) -> FilePlanList:
        """Guarantee the baseline of files exists with correct wiring.
        Missing entries are added; conflicting paths are normalized."""
        by_path = {f.path: f for f in plan.files}

        def ensure(path: str, kind: FileKind, purpose: str, **kwargs) -> None:
            if path in by_path:
                # Patch fields we care about.
                f = by_path[path]
                f.kind = kind
                for k, v in kwargs.items():
                    setattr(f, k, v)
            else:
                by_path[path] = FileGenerationPlan(
                    path=path, kind=kind, purpose=purpose, **kwargs
                )

        # project.godot
        ensure(
            CANONICAL_PATHS["project_godot"],
            FileKind.PROJECT_GODOT,
            purpose="Godot 4 project configuration with input actions and main scene.",
        )

        # player script
        ensure(
            CANONICAL_PATHS["player_script"],
            FileKind.GD_SCRIPT,
            purpose="Player controller. CharacterBody2D with walk/run/jump driven by inputs and SpriteFrames animations.",
            notes=f"Use these abilities verbatim from the brief: {contract.mechanics.character_abilities}",
        )

        # player sprite frames placeholder
        ensure(
            CANONICAL_PATHS["player_sprite_frames"],
            FileKind.RESOURCE,
            purpose="SpriteFrames placeholder. Animations populated later by sprite injection.",
        )

        # player scene
        ensure(
            CANONICAL_PATHS["player_scene"],
            FileKind.SCENE,
            purpose="Player scene: CharacterBody2D + CollisionShape2D + AnimatedSprite2D.",
            depends_on=[
                CANONICAL_PATHS["player_script"],
                CANONICAL_PATHS["player_sprite_frames"],
            ],
            attach_script_to_scene=CANONICAL_PATHS["player_script"],
            deterministic_template="player_scene",
        )

        # main script + scene
        ensure(
            CANONICAL_PATHS["main_script"],
            FileKind.GD_SCRIPT,
            purpose="Main scene root script. Minimal: hooks up references.",
        )
        ensure(
            CANONICAL_PATHS["main_scene"],
            FileKind.SCENE,
            purpose="Main scene: Node2D root, Camera2D, Player instance.",
            depends_on=[
                CANONICAL_PATHS["main_script"],
                CANONICAL_PATHS["player_scene"],
            ],
            attach_script_to_scene=CANONICAL_PATHS["main_script"],
            deterministic_template="main_scene",
        )

        # Enemy: only if the brief mentions enemies.
        if (
            contract.art.enemies
            or "enem" in contract.mechanics.enemy_interaction.lower()
        ):
            ensure(
                CANONICAL_PATHS["enemy_script"],
                FileKind.GD_SCRIPT,
                purpose="Generic enemy controller. CharacterBody2D with simple patrol/chase.",
                notes=f"Enemy interaction brief: {contract.mechanics.enemy_interaction}",
            )
            ensure(
                CANONICAL_PATHS["enemy_scene"],
                FileKind.SCENE,
                purpose="Reusable enemy scene.",
                depends_on=[CANONICAL_PATHS["enemy_script"]],
                attach_script_to_scene=CANONICAL_PATHS["enemy_script"],
                deterministic_template="enemy_scene",
            )

        # Drop anything the LLM invented under res:// or with backslashes or absolute paths.
        clean_files: List[FileGenerationPlan] = []
        for f in by_path.values():
            if f.path.startswith(("/", "res://")) or "\\" in f.path:
                continue
            clean_files.append(f)

        return FilePlanList(files=clean_files)

    def _dependency_order(self, plan: FilePlanList) -> FilePlanList:
        """Stable topological sort. project.godot first, scripts before scenes,
        scenes before main scene."""
        kind_rank = {
            FileKind.PROJECT_GODOT: 0,
            FileKind.RESOURCE: 1,
            FileKind.GD_SCRIPT: 2,
            FileKind.SCENE: 3,
            FileKind.OTHER: 4,
        }
        files = sorted(plan.files, key=lambda f: (kind_rank[f.kind], f.path))

        # Topo-sort within that order, respecting depends_on.
        path_to_file = {f.path: f for f in files}
        visited: set[str] = set()
        ordered: List[FileGenerationPlan] = []

        def visit(p: str) -> None:
            if p in visited or p not in path_to_file:
                return
            visited.add(p)
            for dep in path_to_file[p].depends_on:
                visit(dep)
            ordered.append(path_to_file[p])

        for f in files:
            visit(f.path)

        # Force Main.tscn last among scenes.
        main_scene = CANONICAL_PATHS["main_scene"]
        if any(f.path == main_scene for f in ordered):
            ordered = [f for f in ordered if f.path != main_scene] + [
                path_to_file[main_scene]
            ]

        return FilePlanList(files=ordered)
