"""LangGraph state machine for the game-design conversation flow.

The graph has two nodes:
    extract_info            -- parse the user's latest reply for field values.
    determine_missing_fields -- decide phase and the next field to ask about.

Both routes (gathering / saving) lead to END.  The Streamlit layer reads the
returned state to decide whether to stream a question or trigger save.
"""

import logging
from typing import Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from llm import get_plain_llm
from state import FIELD_KEYS, GameDesignState

logger = logging.getLogger(__name__)


class ExtractedFields(BaseModel):
    """Structured output schema for extracting game-design fields from a user reply."""

    game_mechanic: Optional[str] = Field(
        default=None,
        description="Core game loop, camera mode, gravity, HUD layout, win/lose conditions.",
    )
    enemy_interaction: Optional[str] = Field(
        default=None,
        description="How enemies damage, knock back, or otherwise interact with the player.",
    )
    character_abilities: Optional[str] = Field(
        default=None,
        description="All player actions: movement speed, jump, special abilities, animations.",
    )
    main_character: Optional[str] = Field(
        default=None,
        description="Main character visual appearance, size, color palette, animation states.",
    )
    start_screen_instructions: Optional[str] = Field(
        default=None,
        description="Start screen title style, button layout, and visual effects.",
    )
    enemies: Optional[str] = Field(
        default=None,
        description="Visual descriptions of each enemy type.",
    )
    world_background: Optional[str] = Field(
        default=None,
        description="Static game-world background visuals (sky, city, forest, etc.).",
    )
    tileset_environment: Optional[str] = Field(
        default=None,
        description="Ground tiles, platform surfaces, and environmental objects.",
    )
    main_menu_background: Optional[str] = Field(
        default=None,
        description="Visual scene rendered behind the main menu.",
    )


def extract_info_node(state: GameDesignState) -> dict:
    """Extract game-design field values from the user's latest reply.

    Uses the primary LLM with structured output (``with_structured_output``) to
    parse ``state['latest_user_message']``.  Only non-None values for fields that
    are not yet set in state are merged back.

    On any extraction failure the node returns an empty dict so the graph can
    continue without interruption (graceful degradation).

    Args:
        state: Current game-design state snapshot.

    Returns:
        A (possibly empty) dict of newly discovered field values to merge into state.
    """
    user_text = (state.get("latest_user_message") or "").strip()
    if not user_text:
        return {}

    current_field = state.get("current_question_field")
    field_hint = (
        f"The user was specifically answering a question about '{current_field}'."
        if current_field
        else "Extract any game-design details the user mentioned."
    )

    messages = [
        SystemMessage(
            content=(
                "You are a precise information extractor for a 2D Godot game-design system. "
                f"{field_hint} "
                "Populate only the fields the user clearly described. "
                "Leave all other fields as null."
            )
        ),
        HumanMessage(content=user_text),
    ]

    try:
        extractor = get_plain_llm().with_structured_output(ExtractedFields)
        result: ExtractedFields = extractor.invoke(messages)

        return {
            key: getattr(result, key)
            for key in FIELD_KEYS
            if getattr(result, key, None) and not state.get(key)
        }
    except Exception as exc:
        logger.warning("Structured extraction failed — continuing without update: %s", exc)
        return {}


def determine_missing_fields_node(state: GameDesignState) -> dict:
    """Identify the next unanswered active field and set the conversation phase.

    Returns ``phase='saving'`` when all active fields are collected, otherwise
    ``phase='gathering'`` with ``current_question_field`` pointing to the next
    missing key.

    Args:
        state: Current game-design state snapshot.

    Returns:
        A dict with updated ``phase`` and ``current_question_field`` keys.
    """
    active_indices: list = state.get("active_indices", [0, 1, 2, 3])
    missing = [FIELD_KEYS[i] for i in active_indices if not state.get(FIELD_KEYS[i])]

    if not missing:
        return {"phase": "saving", "current_question_field": None}

    return {"phase": "gathering", "current_question_field": missing[0]}


def _route_phase(state: GameDesignState) -> Literal["saving", "gathering"]:
    """Conditional edge: return the current phase string for graph routing."""
    return state.get("phase", "gathering")  # type: ignore[return-value]


def build_graph():
    """Compile and return the game-design LangGraph state machine.

    Graph topology::

        extract_info → determine_missing_fields → END  (via conditional edge)

    Both the 'gathering' and 'saving' branches route to END.  The Streamlit layer
    reads ``phase`` from the returned state to decide the next UI action.

    Returns:
        A compiled LangGraph ``CompiledGraph`` instance.
    """
    builder = StateGraph(GameDesignState)

    builder.add_node("extract_info", extract_info_node)
    builder.add_node("determine_missing_fields", determine_missing_fields_node)

    builder.set_entry_point("extract_info")
    builder.add_edge("extract_info", "determine_missing_fields")
    builder.add_conditional_edges(
        "determine_missing_fields",
        _route_phase,
        {"gathering": END, "saving": END},
    )

    return builder.compile()
