"""Pydantic contracts. All system-internal data flows through these models."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict

# ---------- Frontend-derived ----------


class MechanicsContract(BaseModel):
    model_config = ConfigDict(extra="ignore")

    game_mechanic: str = ""
    enemy_interaction: str = ""
    start_screen_instructions: str = ""
    character_abilities: List[str] = Field(default_factory=list)


class ArtContract(BaseModel):
    model_config = ConfigDict(extra="ignore")

    base_art_style: str = ""
    main_character: str = ""
    enemies: List[str] = Field(default_factory=list)
    world_background: str = ""
    tileset_environment: str = ""


# ---------- Sprite injection ----------


class SpriteInjectionContract(BaseModel):
    """Stable paths/names the generator promises to use, so a later sprite
    injection system can find/replace assets deterministically."""

    model_config = ConfigDict(extra="ignore")

    player_scene_path: str = "res://scenes/player/Player.tscn"
    player_script_path: str = "res://scripts/player/player.gd"
    player_sprite_frames_path: str = (
        "res://assets/generated/player/player_sprite_frames.tres"
    )
    player_assets_dir: str = "res://assets/generated/player/"

    enemies_assets_dir: str = "res://assets/generated/enemies/"
    tileset_assets_dir: str = "res://assets/generated/tileset/"
    background_assets_dir: str = "res://assets/generated/background/"

    animation_names: List[str] = Field(
        default_factory=lambda: [
            "idle",
            "walk",
            "run",
            "jump",
            "fall",
            "hurt",
            "death",
            "attack",
        ]
    )


# ---------- Top-level request ----------


class RequestManagerContract(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_directory_path: str
    art: ArtContract
    mechanics: MechanicsContract
    sprite_injection: SpriteInjectionContract = Field(
        default_factory=SpriteInjectionContract
    )


# ---------- File generation plan ----------


class FileKind(str, Enum):
    PROJECT_GODOT = "project_godot"  # project.godot
    GD_SCRIPT = "gd_script"  # .gd
    SCENE = "scene"  # .tscn
    RESOURCE = "resource"  # .tres
    OTHER = "other"


class FileGenerationPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str = Field(
        ...,
        description="Path relative to project root, e.g. 'scripts/player/player.gd'",
    )
    kind: FileKind
    purpose: str = Field(
        ..., description="Short human description of what this file is for"
    )
    depends_on: List[str] = Field(
        default_factory=list, description="Other plan paths this file references"
    )
    notes: str = Field("", description="Implementation hints for the writer")
    attach_script_to_scene: Optional[str] = Field(
        default=None,
        description="If this is a .tscn, the project-relative path of a script to attach as its root script. Must already be planned.",
    )
    deterministic_template: Optional[str] = Field(
        default=None,
        description="Token name of a deterministic template to use instead of LLM (e.g. 'player_scene', 'main_scene').",
    )


class FilePlanList(BaseModel):
    model_config = ConfigDict(extra="ignore")
    files: List[FileGenerationPlan]
