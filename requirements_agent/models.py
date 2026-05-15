from typing import List
from pydantic import BaseModel, Field


class RequestManagerContract(BaseModel):
    project_directory_path: str = Field(description="The absolute path to the Godot project folder.")
    game_mechanic: str = Field(description="The core game loop and boundaries. E.g., '2D side-scroller moving right like Mario'.")
    enemy_interaction: str = Field(description="Rules for interacting with enemies. E.g., 'Player takes damage on touch'.")
    start_screen_instructions: str = Field(description="Start screen requirements. E.g., 'Neon title with a blinking Start button'.")
    character_abilities: List[str] = Field(description="Actions the main character can execute. E.g., ['run', 'double_jump'].")


class SpriteGenerationContract(BaseModel):
    project_directory_path: str = Field(description="The absolute path to the Godot project folder.")
    base_art_style: str = Field(
        default="2D pixel art, retro 16-bit style, flat colors, clean background",
        description="HARDCODED global art style.",
    )
    main_character: str = Field(description="Visual description of the main character.")
    enemies: List[str] = Field(default_factory=list, description="Visual descriptions of the enemies.")
    world_background: str = Field(description="Visual description of the game's static background.")
    tileset_environment: str = Field(description="Description of the ground and platforms.")
    main_menu_background: str = Field(description="Visual description of the start screen background.")
