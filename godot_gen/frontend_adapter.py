"""Normalize the two raw frontend response objects into RequestManagerContract.

The frontend strings are intentionally large and descriptive. We do NOT parse
numbers out of them — we just bind them into typed fields and forward to prompts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from contracts import (
    ArtContract,
    MechanicsContract,
    RequestManagerContract,
    SpriteInjectionContract,
)


def to_contract(
    mechanics_obj: Mapping[str, Any],
    art_obj: Mapping[str, Any],
    project_directory_path: str | Path,
) -> RequestManagerContract:
    mechanics = MechanicsContract(
        game_mechanic=str(mechanics_obj.get("game_mechanic", "")),
        enemy_interaction=str(mechanics_obj.get("enemy_interaction", "")),
        start_screen_instructions=str(
            mechanics_obj.get("start_screen_instructions", "")
        ),
        character_abilities=[
            str(x) for x in mechanics_obj.get("character_abilities", []) or []
        ],
    )
    art = ArtContract(
        base_art_style=str(art_obj.get("base_art_style", "")),
        main_character=str(art_obj.get("main_character", "")),
        enemies=[str(x) for x in art_obj.get("enemies", []) or []],
        world_background=str(art_obj.get("world_background", "")),
        tileset_environment=str(art_obj.get("tileset_environment", "")),
    )
    return RequestManagerContract(
        ##project_directory_path=str(Path(project_directory_path).resolve()),
        project_directory_path=r"C:\Users\yarde\Documents\new-game-project-1",
        art=art,
        mechanics=mechanics,
        sprite_injection=SpriteInjectionContract(),
    )
