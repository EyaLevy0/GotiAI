import json
from pathlib import Path

import streamlit as st
from langchain_core.tools import tool

from models import RequestManagerContract, SpriteGenerationContract

AGENT_DATA_PATH = Path(__file__).parent / "agent_data"


@tool
def save_contracts(
    game_mechanic: str,
    enemy_interaction: str,
    character_abilities: str,
    main_character: str,
    start_screen_instructions: str = "",
    enemies: str = "",
    world_background: str = "",
    tileset_environment: str = "",
    main_menu_background: str = "",
) -> str:
    """
    Save the gathered game requirements to two separate JSON contract files.
    Call this ONLY when you have collected enough information for every single field.

    Args:
        game_mechanic: Core game loop description.
        enemy_interaction: How enemies interact with the player.
        start_screen_instructions: Start screen visual and UI requirements.
        character_abilities: Comma-separated actions the player can perform.
        main_character: Visual description of the main character.
        enemies: Comma-separated visual descriptions for each enemy type.
        world_background: Visual description of the static game background.
        tileset_environment: Description of the ground and platforms.
        main_menu_background: Visual description of the main menu background.
    """
    def to_str(v):
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            return json.dumps(v)
        return str(v)

    game_mechanic             = to_str(game_mechanic)
    enemy_interaction         = to_str(enemy_interaction)
    character_abilities       = to_str(character_abilities)
    main_character            = to_str(main_character)
    start_screen_instructions = to_str(start_screen_instructions)
    enemies                   = to_str(enemies)
    world_background          = to_str(world_background)
    tileset_environment       = to_str(tileset_environment)
    main_menu_background      = to_str(main_menu_background)

    abilities_list = [a.strip() for a in character_abilities.replace(",", "\n").splitlines() if a.strip()]
    enemies_list   = [e.strip() for e in enemies.replace(",", "\n").splitlines() if e.strip()]

    project_path_str = str(AGENT_DATA_PATH.parent)

    request_contract = RequestManagerContract(
        project_directory_path=project_path_str,
        game_mechanic=game_mechanic,
        enemy_interaction=enemy_interaction,
        start_screen_instructions=start_screen_instructions,
        character_abilities=abilities_list,
    )
    sprite_contract = SpriteGenerationContract(
        project_directory_path=project_path_str,
        main_character=main_character,
        enemies=enemies_list,
        world_background=world_background,
        tileset_environment=tileset_environment,
        main_menu_background=main_menu_background,
    )

    AGENT_DATA_PATH.mkdir(parents=True, exist_ok=True)
    (AGENT_DATA_PATH / "request_manager_contract.json").write_text(
        request_contract.model_dump_json(indent=2), encoding="utf-8"
    )
    (AGENT_DATA_PATH / "sprite_generation_contract.json").write_text(
        sprite_contract.model_dump_json(indent=2), encoding="utf-8"
    )

    st.session_state.request_contract_data = json.loads(request_contract.model_dump_json())
    st.session_state.sprite_contract_data  = json.loads(sprite_contract.model_dump_json())

    return (
        f"Contracts saved to '{AGENT_DATA_PATH}':\n"
        f"  - request_manager_contract.json\n"
        f"  - sprite_generation_contract.json"
    )
