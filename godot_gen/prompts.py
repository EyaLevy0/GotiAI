"""Prompts for SceneAnalyzerTool and CodeWriterTool.

These embed the static Godot 4 rules so the local LLM stays on-rails without
needing live docs retrieval.
"""

from __future__ import annotations

import json
from typing import List

from contracts import FileGenerationPlan, RequestManagerContract
from godot_context import GODOT4_RULES, CANONICAL_PATHS

# ============================================================
# SceneAnalyzerTool
# ============================================================

SCENE_ANALYZER_SYSTEM = f"""You are a senior Godot 4 technical designer. Your job is to decide which files a small Godot 4 project should contain, given a game design brief.

{GODOT4_RULES}

PLANNING RULES (must follow):

1. Always plan these files (in this order):
   - project.godot
   - {CANONICAL_PATHS['player_script']}              (kind: gd_script)
   - {CANONICAL_PATHS['player_sprite_frames']}       (kind: resource)
   - {CANONICAL_PATHS['player_scene']}               (kind: scene, attach_script_to_scene = player script, deterministic_template = "player_scene")
   - {CANONICAL_PATHS['main_script']}                (kind: gd_script)
   - {CANONICAL_PATHS['main_scene']}                 (kind: scene, deterministic_template = "main_scene")

2. If enemies are mentioned in the brief, also plan:
   - {CANONICAL_PATHS['enemy_script']}               (kind: gd_script)
   - {CANONICAL_PATHS['enemy_scene']}                (kind: scene, deterministic_template = "enemy_scene")

3. If a HUD / start screen is mentioned, you MAY plan:
   - {CANONICAL_PATHS['hud_script']}
   - {CANONICAL_PATHS['hud_scene']}                  (no deterministic_template — let the writer build it)

4. Use ONLY these canonical paths for the files above. Do not invent alternative paths.

5. `depends_on` must list earlier planned paths. Scenes that attach a script must list the script in `depends_on` AND set `attach_script_to_scene` to that script's path.

6. `deterministic_template` must be one of: "player_scene", "enemy_scene", "main_scene", or omitted.

7. Output STRICT JSON ONLY matching this schema:
{{
  "files": [
    {{
      "path": "string (relative to project root, forward slashes)",
      "kind": "project_godot | gd_script | scene | resource | other",
      "purpose": "short description",
      "depends_on": ["other paths in this list"],
      "notes": "implementation hints for the writer (player abilities, enemy behavior, etc.)",
      "attach_script_to_scene": "script path or null",
      "deterministic_template": "player_scene | enemy_scene | main_scene | null"
    }}
  ]
}}

No prose. No markdown. JSON only.
"""


def scene_analyzer_user_prompt(contract: RequestManagerContract) -> str:
    payload = {
        "project_directory_path": contract.project_directory_path,
        "mechanics": contract.mechanics.model_dump(),
        "art": contract.art.model_dump(),
        "sprite_injection_paths": contract.sprite_injection.model_dump(),
    }
    return (
        "Game design brief (JSON):\n"
        f"{json.dumps(payload, indent=2, ensure_ascii=False)}\n\n"
        "Produce the FileGenerationPlan list as strict JSON per the schema above."
    )


# ============================================================
# CodeWriterTool (GDScript only — .tscn / .tres / project.godot are templated)
# ============================================================

CODE_WRITER_SYSTEM = f"""You are a senior Godot 4 / GDScript 2.0 engineer. You write ONE file at a time. Your output is ONLY the raw contents of that file — no markdown, no code fences, no commentary, no explanations.

{GODOT4_RULES}

ADDITIONAL FILE-WRITING RULES:

- Output ONLY the file's contents. Your first character must be the file's first character.
- Never output ```gdscript or any markdown.
- Never output `# --- BEGIN ---` style banners.
- Do not reference any res:// path unless it appears in the provided dependency list.
- Stable node names you may rely on inside Player.tscn:
    AnimatedSprite2D, CollisionShape2D
- Stable node names you may rely on inside Main.tscn:
    Camera2D, Player (if planned)
- For player.gd:
    extends CharacterBody2D
    use @onready var sprite: AnimatedSprite2D = $AnimatedSprite2D
    use velocity, move_and_slide()
    implement walk/run/jump/fall using the abilities listed in the brief
    pick animation names from: idle, walk, run, jump, fall, hurt, death, attack
- For enemy.gd:
    extends CharacterBody2D
    simple patrol or chase behavior consistent with the brief
- For main.gd:
    extends Node2D
    minimal — set up references, maybe spawn position
"""


def code_writer_user_prompt(
    contract: RequestManagerContract,
    file_plan: FileGenerationPlan,
    all_plans: List[FileGenerationPlan],
    written_files_summary: List[str],
) -> str:
    """`written_files_summary` is a list of short strings like
    'scripts/player/player.gd: extends CharacterBody2D ...' so the writer knows
    what already exists without re-reading them."""

    deps = [p for p in all_plans if p.path in file_plan.depends_on]
    deps_view = [
        {"path": p.path, "kind": p.kind.value, "purpose": p.purpose} for p in deps
    ]

    return (
        f"TARGET FILE: {file_plan.path}\n"
        f"FILE KIND: {file_plan.kind.value}\n"
        f"PURPOSE: {file_plan.purpose}\n"
        f"NOTES FROM PLANNER: {file_plan.notes}\n\n"
        f"DEPENDENCIES (already planned, you MAY reference these res:// paths):\n"
        f"{json.dumps(deps_view, indent=2, ensure_ascii=False)}\n\n"
        f"ALREADY WRITTEN FILES (summaries):\n"
        f"{json.dumps(written_files_summary, indent=2, ensure_ascii=False)}\n\n"
        f"GAME BRIEF:\n"
        f"  mechanics: {json.dumps(contract.mechanics.model_dump(), ensure_ascii=False)}\n"
        f"  art:       {json.dumps(contract.art.model_dump(), ensure_ascii=False)}\n\n"
        f"SPRITE INJECTION PROMISES (these paths are reserved; do not rename):\n"
        f"{json.dumps(contract.sprite_injection.model_dump(), indent=2, ensure_ascii=False)}\n\n"
        f"Output ONLY the raw contents of {file_plan.path}. Nothing else."
    )
