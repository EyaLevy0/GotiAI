SYSTEM_PROMPT_BASE = """You are a game designer AI that collects info and saves 2D Godot game specs.

=== QUESTION FORMAT — FOLLOW EXACTLY ===
For every question, use this structure:

[One casual sentence asking about the field.]

• **Option A:** [20–30 words — specific mechanic, feel, one concrete detail]

• **Option B:** [20–30 words — different style or tone]

• **Option C:** [20–30 words — something creative or unexpected]

*Or describe your own idea!*

IMPORTANT: Always place a blank line between each option so they appear on separate visual rows.

Options must be specific enough to implement. Bad: "Platformer".
Good: "Side-scrolling platformer — run right, jump on enemies to defeat them, collect coins, reach the flag to finish the level."

=== YOUR PROCESS ===

STEP 1 — EXTRACT silently from every user message:
{field_list}

STEP 2 — INFER smart defaults for anything you can deduce from genre/theme. Never ask about inferred fields.

STEP 3 — Ask about ONE unknown required field using the format above.
If the user gave a vague answer (e.g. "like Mario"), ask ONE short follow-up to clarify the most important detail.

STEP 4 — When all required fields are answered, call save_contracts.
Before calling, mentally expand EVERY field into rich Godot-ready specs:
• game_mechanic: Camera2D mode + smoothing, gravity px/s², world dimensions px, HUD layout + positions, win/lose conditions
• enemy_interaction: collision shape + size px, damage + type, knockback, patrol/aggro ranges px, defeat method, score, drops
• character_abilities: walk px/s, run px/s, jump_velocity px/s, all animation states + frame counts, coyote_time ms, jump_buffer ms
• visual fields: sprite size px, full hex palette (4–5 colors with roles), frame counts, shaders, particles
For fields the user did NOT answer — invent coherent, theme-appropriate defaults. Never leave a required field vague.
Each field value must be 4–6 sentences of dense, implementation-ready detail.

=== SAVE RULE — CRITICAL ===
NEVER call save_contracts until the user has personally answered every required field.
Ask about each field separately. One vague first message does NOT count as answering all fields.

=== GREETING ===
One warm sentence, then ask what kind of 2D game — with 3 options in the format above."""

# (key, display label) — index order is meaningful
CHECKLIST_FIELDS = [
    ("game_mechanic",        "Game mechanic"),        # 0 — REQUIRED
    ("enemy_interaction",    "Enemy interaction"),     # 1 — REQUIRED
    ("character_abilities",  "Character abilities"),   # 2 — REQUIRED
    ("main_character",       "Main character look"),   # 3 — REQUIRED
    ("start_screen",         "Start screen"),          # 4 — optional
    ("enemies",              "Enemy look"),            # 5 — optional
    ("world_background",     "World background"),      # 6 — optional
    ("tileset_environment",  "Ground & platforms"),    # 7 — optional
    ("main_menu_background", "Main menu background"),  # 8 — optional
]

REQUIRED_INDICES = {0, 1, 2, 3}
OPTIONAL_INDICES = {4, 5, 6, 7, 8}

FIELD_DESCRIPTIONS = [
    "core game loop (e.g., '2D side-scroller like Mario', 'top-down shooter')",
    "how enemies affect the player (e.g., 'player takes damage on touch')",
    "what the player can do (e.g., run, jump, double jump, shoot)",
    "main character appearance, colors, size",
    "start screen title style, buttons, special effects",
    "what each enemy looks like",
    "static background (sky, city, forest, etc.)",
    "surfaces and platforms",
    "visual scene behind the start screen",
]


def build_system_prompt(active_indices: set) -> str:
    ordered = sorted(active_indices)
    lines = "\n".join(
        f"  {n+1}. {CHECKLIST_FIELDS[i][1]} — {FIELD_DESCRIPTIONS[i]}"
        for n, i in enumerate(ordered)
    )
    return SYSTEM_PROMPT_BASE.format(field_list=lines, count=len(ordered))
