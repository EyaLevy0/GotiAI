"""Shared state definitions for the game design conversation state machine."""

from typing import Optional
from typing_extensions import TypedDict

FIELD_KEYS: list[str] = [
    "game_mechanic",            # index 0 — required
    "enemy_interaction",        # index 1 — required
    "character_abilities",      # index 2 — required
    "main_character",           # index 3 — required
    "start_screen_instructions",# index 4 — optional
    "enemies",                  # index 5 — optional
    "world_background",         # index 6 — optional
    "tileset_environment",      # index 7 — optional
    "main_menu_background",     # index 8 — optional
]


class GameDesignState(TypedDict):
    """Persistent state snapshot passed into and out of the LangGraph each turn.

    All nine field values start as None and are filled in as the conversation
    progresses.  The caller must supply every key explicitly when constructing
    the initial state — TypedDict does not support default values.
    """

    # Collected game-design field values; None = not yet gathered.
    game_mechanic: Optional[str]
    enemy_interaction: Optional[str]
    character_abilities: Optional[str]
    main_character: Optional[str]
    start_screen_instructions: Optional[str]
    enemies: Optional[str]
    world_background: Optional[str]
    tileset_environment: Optional[str]
    main_menu_background: Optional[str]

    # Indices into CHECKLIST_FIELDS that are active this session.
    active_indices: list

    # Current conversation phase.
    phase: str  # "gathering" | "saving" | "done"

    # The field key the agent most recently asked about; used to focus extraction.
    current_question_field: Optional[str]

    # Transient: the user's latest raw message.  Set fresh before each graph.invoke().
    latest_user_message: str
