"""
Scene Request Models.

This file defines the approved contract that the Scene Creator pipeline receives
from the Request Manager after the user request has already been clarified and
validated.
"""

from typing import List
from pydantic import BaseModel, Field

"""
contract = RequestManagerContract(
    project_directory_path="C:/game",
    game_mechanic="2D platformer",
    enemy_interaction="damage on touch",
    start_screen_instructions="simple menu",
    character_abilities=["run", "jump"]
)

This creates an object in memory.

Internally:
contract.game_mechanic contains "2D platformer"
"""


class RequestManagerContract(BaseModel):
    """
    Approved game contract created by the Request Manager.

    The Scene Creator pipeline receives this contract after the user request
    was already clarified and validated by the Request Manager.
    """

    # Absolute path to the local Godot project folder on disk.
    project_directory_path: str = Field(
        description=(
            "The absolute path to the Godot project folder where the agent "
            "must save all .tscn, .gd, and image files."
        )
    )

    # Main gameplay loop and movement/camera style.
    game_mechanic: str = Field(
        description=(
            "The hardcoded core game loop and camera/movement boundaries. "
            "Examples: '2D side-scroller moving right like Mario'."
        )
    )

    # Rules for how the player interacts with enemies.
    enemy_interaction: str = Field(
        description=(
            "Specific rules for how the player interacts with enemies. "
            "Example: 'Player takes damage on touch, enemies die if jumped on'."
        )
    )

    # Required elements for the start screen.
    start_screen_instructions: str = Field(
        description=(
            "Specific visual or interactive elements required on the start screen. "
            "Example: 'Neon title with a blinking Start button'."
        )
    )

    # Actions the player character must support.
    character_abilities: List[str] = Field(
        description=(
            "A list of specific actions the main character can execute in the game. "
            "Example: ['run', 'double_jump', 'shoot']."
        )
    )
