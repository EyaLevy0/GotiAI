import json
import os
from pathlib import Path
from typing import List

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from models import RequestManagerContract, SpriteGenerationContract

load_dotenv()

AGENT_DATA_PATH = Path(__file__).parent / "agent_data"

AGENT_AVATARS = ["😎", "🎃", "🦍"]

def agent_avatar(msg_index: int) -> str:
    return AGENT_AVATARS[msg_index % len(AGENT_AVATARS)]

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="GameForge AI",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Prompts & constants
# ---------------------------------------------------------------------------
SYSTEM_PROMPT_BASE = """You are a game designer AI that collects info and saves 2D Godot game specs.

=== QUESTION FORMAT — FOLLOW EXACTLY ===
For every question, use this structure:

[One casual sentence asking about the field.]

• **Option A:** [20–30 words — specific mechanic, feel, one concrete detail]
• **Option B:** [20–30 words — different style or tone]
• **Option C:** [20–30 words — something creative or unexpected]

*Or describe your own idea!*

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

# All 9 fields — index order must match FIELD_TO_ARG
CHECKLIST_FIELDS = [
    ("game_mechanic",        "Game mechanic"),        # 0 — REQUIRED
    ("enemy_interaction",    "Enemy interaction"),     # 1 — REQUIRED
    ("character_abilities",  "Character abilities"),   # 2 — REQUIRED
    ("main_character",       "Main character look"),   # 3 — REQUIRED
    ("start_screen",         "Start screen"),          # 4 — REQUIRED
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

STEP_OPTIONS: dict[int, list[str]] = {
    0: [
        "Side-scroller — gravity flips every 10 seconds",
        "Top-down shooter inside a living organism",
        "Endless runner but the floor is made of teeth",
        "Platformer where the whole level is upside down",
    ],
    1: [
        "Enemies explode into confetti on touch",
        "Player and enemy swap bodies on contact",
        "Touching an enemy reverses your controls",
        "Enemies shrink you to half size on touch",
    ],
    2: [
        "Glitchy VHS-distorted title that flickers",
        "Title floats in zero gravity with spinning letters",
        "Pixel rain falls behind a neon logo",
        "A giant eye blinks — Start button is the pupil",
    ],
    3: [
        "Run + Wall jump + Time slow",
        "Fly + Phase through walls + Black hole throw",
        "Gravity flip + Dash + Shield burst",
        "Teleport + Clone self + Spin attack",
    ],
    4: [
        "A melting clock with legs and a top hat",
        "Tiny astronaut inside a giant hamster ball",
        "A glitching hologram that keeps losing pixels",
        "Upside-down wizard who walks on the ceiling",
    ],
    5: [
        "Living question marks that chase and ask riddles",
        "Mirror copies of the player that mimic moves",
        "Giant floating eyeballs that shoot lasers",
        "Black holes with teeth that slowly drift toward you",
    ],
    6: [
        "Infinite falling sky — no ground exists",
        "Inside a neon circuit board with pulsing electricity",
        "Underwater but the water is glowing purple acid",
        "A city built on the backs of sleeping giants",
    ],
    7: [
        "Platforms made of giant frozen music notes",
        "Crumbling neon signs suspended in mid-air",
        "Rotating gears and pistons as ground tiles",
        "Floating islands made of shattered mirror glass",
    ],
    8: [
        "An infinite void with a single falling pixel",
        "Slow-motion aurora with floating debris",
        "A massive eye watches from behind the menu",
        "Glitchy static slowly revealing a hidden landscape",
    ],
}

# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------
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

    game_mechanic            = to_str(game_mechanic)
    enemy_interaction        = to_str(enemy_interaction)
    character_abilities      = to_str(character_abilities)
    main_character           = to_str(main_character)
    start_screen_instructions= to_str(start_screen_instructions)
    enemies                  = to_str(enemies)
    world_background         = to_str(world_background)
    tileset_environment      = to_str(tileset_environment)
    main_menu_background     = to_str(main_menu_background)

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

    # Store contracts in session state so the UI can display them
    st.session_state.request_contract_data  = json.loads(request_contract.model_dump_json())
    st.session_state.sprite_contract_data   = json.loads(sprite_contract.model_dump_json())

    return (
        f"Contracts saved to '{AGENT_DATA_PATH}':\n"
        f"  - request_manager_contract.json\n"
        f"  - sprite_generation_contract.json"
    )

# ---------------------------------------------------------------------------
# LLM — cached instances, priority: OpenRouter → Gemini → Groq → Ollama
# ---------------------------------------------------------------------------
@st.cache_resource
def _get_cached_llm(with_tools: bool):
    """Create LLM once and reuse across reruns."""
    from langchain_openai import ChatOpenAI
    if os.getenv("OPENROUTER_API_KEY"):
        llm = ChatOpenAI(
            model="meta-llama/llama-3.3-70b-instruct",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            temperature=0.3,
        )
        return llm.bind_tools([save_contracts]) if with_tools else llm
    if os.getenv("GOOGLE_API_KEY"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.3)
        return llm.bind_tools([save_contracts]) if with_tools else llm
    if os.getenv("GROQ_API_KEY"):
        from langchain_groq import ChatGroq
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.3)
        return llm.bind_tools([save_contracts]) if with_tools else llm
    from langchain_ollama import ChatOllama
    llm = ChatOllama(model="qwen2.5:7b")
    return llm.bind_tools([save_contracts]) if with_tools else llm

def _invoke_with_fallback(messages, with_tools=True):
    try:
        return _get_cached_llm(with_tools).invoke(messages)
    except Exception as e:
        msg = str(e).lower()
        if "429" in msg or "rate_limit" in msg or "rate limit" in msg or "quota" in msg:
            # rate-limited — try Gemini directly
            if os.getenv("GOOGLE_API_KEY"):
                from langchain_google_genai import ChatGoogleGenerativeAI
                llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.3)
                llm = llm.bind_tools([save_contracts]) if with_tools else llm
                return llm.invoke(messages)
        raise

def _stream_with_fallback(messages):
    try:
        yield from _get_cached_llm(True).stream(messages)
    except Exception as e:
        msg = str(e).lower()
        if "429" in msg or "rate_limit" in msg or "rate limit" in msg or "quota" in msg:
            if os.getenv("GOOGLE_API_KEY"):
                from langchain_google_genai import ChatGoogleGenerativeAI
                llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.3)
                yield from llm.bind_tools([save_contracts]).stream(messages)
                return
        raise

def get_llm():
    return _get_cached_llm(True)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
# Maps CHECKLIST_FIELDS index → save_contracts argument name
# Maps CHECKLIST_FIELDS index → save_contracts argument name
FIELD_TO_ARG = [
    "game_mechanic",           # 0
    "enemy_interaction",       # 1
    "character_abilities",     # 2
    "main_character",          # 3
    "start_screen_instructions", # 4
    "enemies",                 # 5
    "world_background",        # 6
    "tileset_environment",     # 7
    "main_menu_background",    # 8
]

def reset_session():
    for key in ["lc_messages", "chat_history", "contracts_saved", "pending_input",
                "request_contract_data", "sprite_contract_data", "answers",
                "custom_fields", "completed_steps", "enabled_optional"]:
        st.session_state.pop(key, None)
    st.rerun()

def re_save_contracts():
    """Re-write JSON files from edited answers in session state."""
    a = st.session_state.answers
    cf = st.session_state.get("custom_fields", [])

    abilities_list = [x.strip() for x in a.get(3, "").replace(",", "\n").splitlines() if x.strip()]
    enemies_list   = [x.strip() for x in a.get(5, "").replace(",", "\n").splitlines() if x.strip()]

    req = RequestManagerContract(
        project_directory_path=str(AGENT_DATA_PATH.parent),
        game_mechanic=a.get(0, ""),
        enemy_interaction=a.get(1, ""),
        start_screen_instructions=a.get(2, ""),
        character_abilities=abilities_list,
    )
    spr = SpriteGenerationContract(
        project_directory_path=str(AGENT_DATA_PATH.parent),
        main_character=a.get(4, ""),
        enemies=enemies_list,
        world_background=a.get(6, ""),
        tileset_environment=a.get(7, ""),
        main_menu_background=a.get(8, ""),
    )

    req_data = json.loads(req.model_dump_json())
    spr_data = json.loads(spr.model_dump_json())
    if cf:
        req_data["extra_fields"] = {f["label"]: f["value"] for f in cf}
        spr_data["extra_fields"] = {f["label"]: f["value"] for f in cf}

    AGENT_DATA_PATH.mkdir(parents=True, exist_ok=True)
    (AGENT_DATA_PATH / "request_manager_contract.json").write_text(
        json.dumps(req_data, indent=2), encoding="utf-8"
    )
    (AGENT_DATA_PATH / "sprite_generation_contract.json").write_text(
        json.dumps(spr_data, indent=2), encoding="utf-8"
    )
    st.session_state.request_contract_data = req_data
    st.session_state.sprite_contract_data  = spr_data

def init_session():
    if "lc_messages" not in st.session_state:
        st.session_state.lc_messages            = [SystemMessage(content=build_system_prompt(REQUIRED_INDICES))]
        st.session_state.chat_history           = []
        st.session_state.contracts_saved        = False
        st.session_state.pending_input          = None
        st.session_state.request_contract_data  = None
        st.session_state.sprite_contract_data   = None
        st.session_state.answers                = {}
        st.session_state.custom_fields          = []
        st.session_state.completed_steps        = 0
        st.session_state.enabled_optional       = set()
        active = REQUIRED_INDICES | st.session_state.enabled_optional
        st.session_state.lc_messages[0] = SystemMessage(content=build_system_prompt(active))
        greeting = (
            "Welcome to **GameForge AI**! 😎\n\n"
            "I'll help you design your 2D Godot game and generate the full spec files automatically.\n\n"
            "**What kind of 2D game do you want to make?**\n"
            "*(e.g. platformer, top-down shooter, endless runner, puzzle)*"
        )
        st.session_state.chat_history.append({"role": "assistant", "content": greeting})

    # Back-compat: add keys if session was created before this version
    if "answers" not in st.session_state:
        st.session_state.answers = {}
    if "custom_fields" not in st.session_state:
        st.session_state.custom_fields = []
    if "completed_steps" not in st.session_state:
        st.session_state.completed_steps = 0
    if "enabled_optional" not in st.session_state:
        st.session_state.enabled_optional = set()

init_session()

# ---------------------------------------------------------------------------
# CSS — glassmorphism + anti-gravity theme
# ---------------------------------------------------------------------------
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=Inter:wght@400;500;600&display=swap');

  * { box-sizing: border-box; }

  /* Background */
  .stApp {
      min-height: 100vh;
      background: #04050f;
      color: #e8eaf6;
      overflow-x: hidden;
  }
  .stApp::before {
      content: '';
      position: fixed; inset: 0;
      background:
          radial-gradient(ellipse 60% 50% at 20% 50%, rgba(100,0,200,0.4) 0%, transparent 70%),
          radial-gradient(ellipse 50% 60% at 80% 20%, rgba(0,100,220,0.35) 0%, transparent 70%),
          radial-gradient(ellipse 55% 45% at 55% 85%, rgba(0,180,200,0.25) 0%, transparent 65%);
      animation: aurora 14s ease-in-out infinite alternate;
      pointer-events: none; z-index: 0;
  }
  @keyframes aurora {
      0%   { opacity: 0.5; transform: scale(1) rotate(0deg); }
      50%  { opacity: 0.9; transform: scale(1.1) rotate(2deg); }
      100% { opacity: 0.5; transform: scale(1) rotate(0deg); }
  }

  /* Hide default header */
  [data-testid="stHeader"]  { background: transparent !important; }
  [data-testid="stToolbar"] { display: none; }
  #MainMenu { display: none; }
  [data-testid="stDecoration"] { display: none; }

  /* Hide sidebar entirely — we use columns instead */
  [data-testid="stSidebar"]               { display: none !important; }
  [data-testid="stSidebarCollapsedControl"]{ display: none !important; }

  /* Left column — stick to top */
  [data-testid="stHorizontalBlock"] > [data-testid="column"]:first-child {
      align-self: flex-start !important;
      position: sticky !important;
      top: 1rem !important;
  }

  /* Left panel column — glassmorphism */
  .left-panel {
      background: rgba(6, 4, 22, 0.7);
      backdrop-filter: blur(24px) saturate(160%);
      border-right: 1px solid rgba(123,47,255,0.2);
      border-radius: 16px;
      padding: 1.4rem 1.2rem;
  }

  /* Sidebar brand */
  .sb-brand {
      font-family: 'Orbitron', sans-serif;
      font-size: 1.1rem; font-weight: 900;
      letter-spacing: 1px; color: #fff;
      padding: 0.4rem 0 1.2rem;
      border-bottom: 1px solid rgba(123,47,255,0.25);
      margin-bottom: 1rem;
  }
  .sb-brand .accent { color: #7df9ff; }

  /* Progress bar */
  .pbar-wrap { margin: 0 0 1.2rem; }
  .pbar-labels {
      display: flex; justify-content: space-between;
      font-size: 0.72rem; color: rgba(255,255,255,0.4);
      font-family: 'Inter', sans-serif; margin-bottom: 6px;
  }
  .pbar-bg { background: rgba(255,255,255,0.08); border-radius: 999px; height: 5px; overflow: hidden; }
  .pbar-fill {
      height: 5px; border-radius: 999px;
      background: linear-gradient(90deg, #7b2fff, #7df9ff);
      box-shadow: 0 0 8px #7b2fff88;
      transition: width 0.6s cubic-bezier(.4,0,.2,1);
  }

  /* Stepper */
  .stepper { display: flex; flex-direction: column; position: relative; margin-top: 0.5rem; }
  .step-item {
      display: flex; align-items: flex-start; gap: 12px;
      padding: 6px 0; position: relative;
  }
  .step-item:not(:last-child)::after {
      content: '';
      position: absolute; left: 12px; top: 30px;
      width: 2px; bottom: -6px;
      background: rgba(255,255,255,0.07);
      transition: background 0.6s ease;
  }
  .step-item.done:not(:last-child)::after {
      background: linear-gradient(180deg, #7b2fff 0%, rgba(123,47,255,0.25) 100%);
  }
  .step-bubble {
      width: 26px; height: 26px; border-radius: 50%; flex-shrink: 0;
      display: flex; align-items: center; justify-content: center;
      font-size: 0.68rem; font-weight: 700; position: relative;
      transition: all 0.4s cubic-bezier(0.34,1.56,0.64,1);
  }
  .step-bubble.done {
      background: linear-gradient(135deg, #7b2fff, #a78bfa);
      color: #fff;
      box-shadow: 0 0 14px rgba(123,47,255,0.7);
      animation: popBubble 0.5s cubic-bezier(0.34,1.56,0.64,1);
  }
  .step-bubble.active {
      background: rgba(123,47,255,0.12);
      border: 2px solid #7b2fff; color: #fff;
  }
  .step-bubble.active::after {
      content: ''; position: absolute; inset: -5px; border-radius: 50%;
      border: 2px solid rgba(123,47,255,0.45);
      animation: ping 1.6s cubic-bezier(0,0,0.2,1) infinite;
  }
  .step-bubble.pending {
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.1);
      color: rgba(255,255,255,0.2);
  }
  .step-label { font-family: 'Inter', sans-serif; font-size: 0.79rem; padding-top: 3px; line-height: 1.3; }
  .step-label.done    { color: #c4b5fd; }
  .step-label.active  { color: #fff; font-weight: 600; }
  .step-label.pending { color: rgba(255,255,255,0.22); }
  @keyframes popBubble {
      0%   { transform: scale(0.4); }
      60%  { transform: scale(1.25); }
      100% { transform: scale(1); }
  }
  @keyframes ping {
      0%   { transform: scale(1); opacity: 0.7; }
      100% { transform: scale(1.9); opacity: 0; }
  }

  /* Quick pick label */
  .options-label {
      font-family: 'Inter', sans-serif;
      font-size: 0.7rem; color: rgba(255,255,255,0.35);
      letter-spacing: 2px; text-transform: uppercase;
      margin: 1.2rem 0 0.5rem;
  }

  /* Quick pick buttons — left column */
  [data-testid="stHorizontalBlock"] > [data-testid="column"]:first-child button {
      background: rgba(123,47,255,0.1) !important;
      border: 1px solid rgba(123,47,255,0.3) !important;
      border-radius: 10px !important;
      color: #c4b5fd !important;
      font-family: 'Inter', sans-serif !important;
      font-size: 0.78rem !important;
      transition: all 0.2s ease !important;
      margin-bottom: 4px !important;
      text-align: left !important;
  }
  [data-testid="stHorizontalBlock"] > [data-testid="column"]:first-child button:hover {
      background: rgba(123,47,255,0.3) !important;
      border-color: #7b2fff !important;
      color: #fff !important;
      box-shadow: 0 0 12px rgba(123,47,255,0.4) !important;
      transform: translateX(3px) !important;
  }

  /* Main area — glassmorphism panel */
  [data-testid="stMainBlockContainer"] {
      background: rgba(4, 5, 20, 0.5) !important;
      backdrop-filter: blur(18px) saturate(120%) !important;
      border-left: 1px solid rgba(123,47,255,0.1);
      min-height: 100vh; position: relative; z-index: 10;
  }

  /* Hero */
  .hero {
      padding: 2rem 0 1.2rem;
      border-bottom: 1px solid rgba(123,47,255,0.15);
      margin-bottom: 1.5rem;
  }
  .hero-tag {
      font-family: 'Orbitron', sans-serif;
      font-size: 0.6rem; letter-spacing: 3px;
      color: #7df9ff; text-transform: uppercase;
      margin-bottom: 0.5rem;
  }
  .hero h1 {
      font-family: 'Orbitron', sans-serif;
      font-size: 2.1rem; font-weight: 900;
      margin: 0 0 0.4rem;
      background: linear-gradient(100deg, #fff 0%, #a78bfa 50%, #7df9ff 100%);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      animation: glow-text 4s ease-in-out infinite alternate;
  }
  @keyframes glow-text {
      from { filter: brightness(1); }
      to   { filter: brightness(1.2) drop-shadow(0 0 10px #7b2fff55); }
  }
  .hero p { font-family: 'Inter', sans-serif; font-size: 0.87rem; color: rgba(255,255,255,0.45); margin: 0; }

  /* Floating pixels */
  .px { display: inline-block; width: 7px; height: 7px; border-radius: 2px; margin-right: 7px; }
  .px.a { background:#7b2fff; animation: floatPx 3s ease-in-out infinite alternate; }
  .px.b { background:#7df9ff; animation: floatPx 3s ease-in-out infinite alternate; animation-delay:.7s; }
  .px.c { background:#a78bfa; animation: floatPx 3s ease-in-out infinite alternate; animation-delay:1.4s; }
  @keyframes floatPx { from { transform: translateY(0) rotate(0deg); } to { transform: translateY(-8px) rotate(18deg); } }

  /* Rising particles */
  .particle {
      position: fixed; border-radius: 3px;
      pointer-events: none; z-index: 1;
      animation: riseUp linear infinite;
  }
  @keyframes riseUp {
      0%   { transform: translateY(100vh) scale(0.4); opacity: 0; }
      10%  { opacity: 0.8; }
      90%  { opacity: 0.5; }
      100% { transform: translateY(-20vh) scale(1.2); opacity: 0; }
  }

  /* Chat messages — glassmorphism */
  [data-testid="stChatMessage"] {
      background: rgba(255,255,255,0.04) !important;
      border: 1px solid rgba(123,47,255,0.15) !important;
      border-radius: 16px !important;
      margin-bottom: 0.6rem !important;
      padding: 0.8rem 1rem !important;
      backdrop-filter: blur(10px) !important;
      font-family: 'Inter', sans-serif !important;
      animation: msgIn 0.3s ease-out;
  }
  @keyframes msgIn {
      from { opacity: 0; transform: translateY(8px); }
      to   { opacity: 1; transform: translateY(0); }
  }

  /* Bottom bar */
  [data-testid="stBottom"],
  [data-testid="stBottom"] > div,
  [data-testid="stBottom"] > div > div {
      background: rgba(4, 5, 20, 0.88) !important;
      backdrop-filter: blur(20px) !important;
      border-top: 1px solid rgba(123,47,255,0.2) !important;
      box-shadow: 0 -6px 30px rgba(80,0,200,0.12) !important;
  }

  /* Chat input */
  [data-testid="stChatInput"] textarea {
      background: rgba(123,47,255,0.08) !important;
      border: 1px solid rgba(123,47,255,0.35) !important;
      border-radius: 14px !important;
      color: #fff !important;
      font-family: 'Inter', sans-serif !important;
      font-size: 0.95rem !important;
  }
  [data-testid="stChatInput"] textarea::placeholder { color: rgba(255,255,255,0.25) !important; }
  [data-testid="stChatInput"] textarea:focus {
      border-color: #7b2fff !important;
      box-shadow: 0 0 14px rgba(123,47,255,0.3) !important;
      outline: none !important;
  }
  *, *:focus, *:focus-within, *:focus-visible { outline: none !important; }
  [data-baseweb], [data-baseweb]:focus, [data-baseweb]:focus-within {
      border-color: transparent !important; box-shadow: none !important;
  }

  /* Thinking dots */
  .dots { display: inline-block; }
  @keyframes blink { 0%,100% { opacity: 0.2; } 50% { opacity: 1; } }
  .dots { animation: blink 1.2s ease-in-out infinite; }

  /* Finish line card */
  .finish-card {
      background: rgba(74,222,128,0.06);
      border: 1px solid rgba(74,222,128,0.3);
      border-radius: 16px; padding: 1.5rem 2rem;
      text-align: center; margin-top: 1rem;
      font-family: 'Inter', sans-serif;
  }
  .finish-card h2 {
      font-family: 'Orbitron', sans-serif;
      font-size: 1.3rem; color: #4ade80; margin: 0 0 0.4rem;
  }
  .finish-card p { color: rgba(255,255,255,0.5); font-size: 0.85rem; margin: 0; }

  /* Success / info */
  [data-testid="stSuccess"] {
      background: rgba(74,222,128,0.08) !important;
      border: 1px solid rgba(74,222,128,0.3) !important;
      border-radius: 12px !important; color: #4ade80 !important;
  }
  [data-testid="stInfo"] {
      background: rgba(123,47,255,0.08) !important;
      border: 1px solid rgba(123,47,255,0.3) !important;
      border-radius: 12px !important;
  }
  [data-testid="stExpander"] {
      background: rgba(255,255,255,0.03) !important;
      border: 1px solid rgba(123,47,255,0.2) !important;
      border-radius: 12px !important;
  }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# (light mode removed)
# ---------------------------------------------------------------------------
if False:
    st.markdown("""
<style>
  /* ── Light mode — Gmail-inspired: clean, flat, white ── */

  /* Kill the aurora and dark background entirely */
  .stApp {
      background: #f6f8fc !important;
      color: #202124 !important;
  }
  .stApp::before { display: none !important; }

  /* Hide floating particles in light mode */
  .particle { display: none !important; }

  /* ── Left panel — light gray sidebar like Gmail ── */
  .left-panel {
      background: #ffffff !important;
      backdrop-filter: none !important;
      border: none !important;
      border-radius: 12px !important;
      box-shadow: 0 1px 3px rgba(60,64,67,0.12), 0 2px 8px rgba(60,64,67,0.08) !important;
  }
  .sb-brand {
      color: #202124 !important;
      border-bottom: 1px solid #e8eaed !important;
  }
  .sb-brand .accent { color: #7b2fff !important; }

  /* Progress bar */
  .pbar-labels { color: #5f6368 !important; }
  .pbar-bg { background: #e8eaed !important; }

  /* Stepper */
  .step-label.done    { color: #6d28d9 !important; }
  .step-label.active  { color: #202124 !important; font-weight: 600 !important; }
  .step-label.pending { color: #9aa0a6 !important; }
  .step-item:not(:last-child)::after { background: #e8eaed !important; }
  .step-bubble.pending {
      background: #f1f3f4 !important;
      border: 1px solid #dadce0 !important;
      color: #9aa0a6 !important;
  }
  .step-bubble.active {
      background: #f3eeff !important;
      border: 2px solid #7b2fff !important;
      color: #7b2fff !important;
  }
  .options-label { color: #9aa0a6 !important; letter-spacing: 1.5px !important; }

  /* Left-column buttons — flat pill style */
  [data-testid="stHorizontalBlock"] > [data-testid="column"]:first-child button {
      background: #f1f3f4 !important;
      border: 1px solid #dadce0 !important;
      border-radius: 20px !important;
      color: #3c4043 !important;
      font-size: 0.78rem !important;
      transition: background 0.15s ease !important;
      transform: none !important;
      box-shadow: none !important;
  }
  [data-testid="stHorizontalBlock"] > [data-testid="column"]:first-child button:hover {
      background: #e8eaed !important;
      border-color: #bdc1c6 !important;
      color: #202124 !important;
      transform: none !important;
      box-shadow: none !important;
  }

  /* ── Main content area — white card ── */
  [data-testid="stMainBlockContainer"] {
      background: #f6f8fc !important;
      backdrop-filter: none !important;
      border-left: none !important;
  }

  /* Hero */
  .hero { border-bottom: 1px solid #e8eaed !important; }
  .hero-tag { color: #7b2fff !important; opacity: 0.8; }
  .hero h1 {
      background: linear-gradient(100deg, #202124 0%, #7b2fff 60%, #4285f4 100%) !important;
      -webkit-background-clip: text !important;
      -webkit-text-fill-color: transparent !important;
      animation: none !important;
      filter: none !important;
  }
  .hero p { color: #5f6368 !important; }
  .px.a { background: #7b2fff !important; }
  .px.b { background: #4285f4 !important; }
  .px.c { background: #a78bfa !important; }

  /* Chat messages — white card with Gmail-style shadow */
  [data-testid="stChatMessage"] {
      background: #ffffff !important;
      border: 1px solid #e8eaed !important;
      border-radius: 12px !important;
      box-shadow: 0 1px 2px rgba(60,64,67,0.1) !important;
      backdrop-filter: none !important;
      color: #202124 !important;
      animation: none !important;
  }

  /* Bottom bar */
  [data-testid="stBottom"],
  [data-testid="stBottom"] > div,
  [data-testid="stBottom"] > div > div {
      background: #ffffff !important;
      backdrop-filter: none !important;
      border-top: 1px solid #e8eaed !important;
      box-shadow: 0 -1px 3px rgba(60,64,67,0.1) !important;
  }

  /* Chat input — clean white box */
  [data-testid="stChatInput"] textarea {
      background: #f1f3f4 !important;
      border: 1px solid #dadce0 !important;
      border-radius: 24px !important;
      color: #202124 !important;
      box-shadow: none !important;
  }
  [data-testid="stChatInput"] textarea::placeholder { color: #9aa0a6 !important; }
  [data-testid="stChatInput"] textarea:focus {
      background: #ffffff !important;
      border-color: #7b2fff !important;
      box-shadow: 0 0 0 2px rgba(123,47,255,0.12) !important;
  }

  /* Finish card */
  .finish-card {
      background: #e6f4ea !important;
      border: 1px solid #ceead6 !important;
  }
  .finish-card h2 { color: #137333 !important; }
  .finish-card p  { color: #5f6368 !important; }

  /* Expanders */
  [data-testid="stExpander"] {
      background: #ffffff !important;
      border: 1px solid #e8eaed !important;
      backdrop-filter: none !important;
  }

  /* Info / success */
  [data-testid="stInfo"] {
      background: #e8f0fe !important;
      border: 1px solid #c5d8fd !important;
      color: #1a73e8 !important;
  }
  [data-testid="stSuccess"] {
      background: #e6f4ea !important;
      border: 1px solid #ceead6 !important;
      color: #137333 !important;
  }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Emoji rain animation
# ---------------------------------------------------------------------------
def emoji_rain():
    components.html("""
    <style>
      #rain-container {
        position: fixed;
        top: 0; left: 0;
        width: 100vw; height: 100vh;
        pointer-events: none;
        z-index: 99999;
        overflow: hidden;
      }
      .emoji-drop {
        position: absolute;
        top: -80px;
        font-size: 2rem;
        animation: fall linear forwards;
        user-select: none;
      }
      @keyframes fall {
        0%   { transform: translateY(0) rotate(0deg);   opacity: 1; }
        80%  { opacity: 1; }
        100% { transform: translateY(110vh) rotate(360deg); opacity: 0; }
      }
    </style>
    <div id="rain-container"></div>
    <script>
      const emojis   = ["🤖","👾","👽","🧟","🚀","🎮","💥","🛸","⚡","🔫","🧠","🪐"];
      const container = document.getElementById("rain-container");
      const COUNT     = 60;

      for (let i = 0; i < COUNT; i++) {
        const el       = document.createElement("span");
        el.className   = "emoji-drop";
        el.textContent = emojis[Math.floor(Math.random() * emojis.length)];

        const left     = Math.random() * 100;
        const delay    = Math.random() * 3;
        const duration = 2 + Math.random() * 3;
        const size     = 1.2 + Math.random() * 1.8;

        el.style.left            = `${left}vw`;
        el.style.animationDelay  = `${delay}s`;
        el.style.animationDuration = `${duration}s`;
        el.style.fontSize        = `${size}rem`;

        container.appendChild(el);
      }

      // Remove container after all drops have landed
      setTimeout(() => container.remove(), 7000);
    </script>
    """, height=0)

# ---------------------------------------------------------------------------
# Derived state
# ---------------------------------------------------------------------------
active_indices  = sorted(REQUIRED_INDICES | st.session_state.enabled_optional)
total_active    = len(active_indices)
user_turns      = len([m for m in st.session_state.chat_history if m["role"] == "user"])
completed       = min(user_turns, total_active)
progress_pct    = min(int((completed / total_active) * 100), 100) if total_active else 0

# ---------------------------------------------------------------------------
# Two-column layout
# ---------------------------------------------------------------------------
left_col, right_col = st.columns([1, 2.8], gap="medium")

# ── Left panel ──────────────────────────────────────────────────────────────
with left_col:
    st.markdown('<div class="left-panel">', unsafe_allow_html=True)

    st.markdown('<div class="sb-brand">GAME<span class="accent">FORGE</span> AI</div>', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="pbar-wrap">
      <div class="pbar-labels"><span>Progress</span><span>{completed} / {total_active}</span></div>
      <div class="pbar-bg"><div class="pbar-fill" style="width:{progress_pct}%"></div></div>
    </div>
    """, unsafe_allow_html=True)

    # ── Stepper (active fields only) ────────────────────────────────────────
    stepper_html = '<div class="stepper">'
    for step_num, field_idx in enumerate(active_indices):
        label = CHECKLIST_FIELDS[field_idx][1]
        is_req = field_idx in REQUIRED_INDICES
        badge = "" if is_req else '<span style="font-size:0.6rem;opacity:0.5;margin-left:4px">opt</span>'
        if step_num < completed:
            css, icon = "done", "✓"
        elif step_num == completed:
            css, icon = "active", str(step_num + 1)
        else:
            css, icon = "pending", str(step_num + 1)
        stepper_html += f"""
        <div class="step-item {css}">
          <div class="step-bubble {css}">{icon}</div>
          <div class="step-label {css}">{label}{badge}</div>
        </div>"""
    stepper_html += '</div>'
    st.markdown(stepper_html, unsafe_allow_html=True)

    # ── Optional fields ──────────────────────────────────────────────────────
    st.markdown('<div class="options-label" style="margin-top:1.2rem">Optional fields</div>', unsafe_allow_html=True)
    for field_idx in sorted(OPTIONAL_INDICES):
        label = CHECKLIST_FIELDS[field_idx][1]
        enabled = field_idx in st.session_state.enabled_optional
        btn_label = f"✓ {label}" if enabled else f"＋ {label}"
        btn_style = "primary" if enabled else "secondary"
        if st.button(btn_label, key=f"opt_toggle_{field_idx}",
                     use_container_width=True, type=btn_style):
            if enabled:
                st.session_state.enabled_optional.discard(field_idx)
            else:
                st.session_state.enabled_optional.add(field_idx)
            # Update system message with new active fields
            new_active = REQUIRED_INDICES | st.session_state.enabled_optional
            st.session_state.lc_messages[0] = SystemMessage(
                content=build_system_prompt(new_active)
            )
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("↺ Start over", key="reset_btn", use_container_width=True):
        reset_session()

    st.markdown('</div>', unsafe_allow_html=True)

# ── Right panel ─────────────────────────────────────────────────────────────
with right_col:
    st.markdown("""
    <div aria-hidden="true">
      <div class="particle" style="width:5px;height:5px;left:12%;background:#7b2fff;animation-duration:9s;animation-delay:0s;"></div>
      <div class="particle" style="width:3px;height:3px;left:35%;background:#7df9ff;animation-duration:13s;animation-delay:2s;"></div>
      <div class="particle" style="width:6px;height:6px;left:60%;background:#a78bfa;animation-duration:8s;animation-delay:1s;"></div>
      <div class="particle" style="width:4px;height:4px;left:82%;background:#7df9ff;animation-duration:15s;animation-delay:4s;"></div>
    </div>
    <div class="hero">
      <div class="hero-tag">
        <span class="px a"></span><span class="px b"></span><span class="px c"></span>
        Anti-Gravity Game Studio
      </div>
      <h1>Design Your 2D Godot Game</h1>
      <p>Answer one question at a time — I'll generate the full Godot spec files automatically.</p>
    </div>
    """, unsafe_allow_html=True)

    _ai_idx = 0
    for msg in st.session_state.chat_history:
        if msg["role"] == "assistant":
            with st.chat_message("assistant", avatar=agent_avatar(_ai_idx)):
                st.write(msg["content"])
            _ai_idx += 1

    if st.session_state.contracts_saved:
        st.markdown("""
        <div class="finish-card">
          <h2>🏁 Game Spec Complete!</h2>
          <p>Both contract files have been generated and saved.</p>
        </div>
        """, unsafe_allow_html=True)

        emoji_rain()

        col_a, col_b = st.columns(2)
        with col_a:
            with st.expander("📋 Request Manager Contract", expanded=False):
                st.json(st.session_state.request_contract_data)
        with col_b:
            with st.expander("🎨 Sprite Generation Contract", expanded=False):
                st.json(st.session_state.sprite_contract_data)

        st.info(f"📁 Saved to: `{AGENT_DATA_PATH}`")

        if st.button("🚀 Proceed to Scene Generation", type="primary", use_container_width=True):
            st.success("✅ Handing off to the Scene Generation agent...")

        st.stop()

    # Container for streaming response — placed BEFORE chat_input so it renders above it
    stream_container = st.container()

    if st.session_state.pending_input:
        pending = st.session_state.pending_input
        st.session_state.pending_input = None
        prompt_to_process = pending
    else:
        prompt_to_process = st.chat_input("Write your answer...")

    def process_message(prompt: str):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        st.session_state.lc_messages.append(HumanMessage(content=prompt))
        _next_avatar = agent_avatar(sum(1 for m in st.session_state.chat_history if m["role"] == "assistant"))

        user_msg_count = len([m for m in st.session_state.chat_history if m["role"] == "user"])
        should_save = user_msg_count >= total_active
        messages_to_send = list(st.session_state.lc_messages)
        force_msg = HumanMessage(content=(
            f"You now have answers for all {total_active} required fields. "
            "Call save_contracts NOW. For EVERY field, write rich expanded Godot specs — "
            "do NOT copy the user's words verbatim. Instead, expand them into full technical detail:\n"
            "• game_mechanic: Camera2D mode + smoothing, gravity px/s², world width px, "
            "HUD elements with screen positions, win/lose conditions, level structure\n"
            "• enemy_interaction: collision shape + exact px size, damage amount + type, "
            "knockback force, patrol range px, aggro radius px, defeat method, score, drops\n"
            "• character_abilities: walk px/s, run px/s, jump_velocity px/s, max jump height px, "
            "all animation states with frame counts (idle:4f run:8f jump:3f fall:2f hurt:2f death:4f), "
            "coyote_time ms, jump_buffer ms, any special ability cooldowns\n"
            "• main_character: sprite size px, full color palette with 4-5 hex codes and roles, "
            "spritesheet layout, shader effects, particle effects\n"
            "• All visual fields: sprite sizes, hex palettes, frame counts, animations\n"
            "For any field the user did NOT answer — invent smart, coherent defaults that fit the game theme. "
            "Every field must be 4-6 sentences of dense detail. No empty strings for required fields."
        ))
        if should_save:
            messages_to_send = messages_to_send + [force_msg]

        # ── When all fields collected: invoke directly (no stream) ───────────
        MARKER = "<<STEP_DONE>>"
        response = None
        raw_content = ""
        display_content = ""

        if should_save:
            with stream_container:
                with st.chat_message("assistant", avatar=_next_avatar):
                    placeholder = st.empty()
                    placeholder.markdown(
                        '<span style="color:rgba(255,255,255,0.35);font-style:italic">'
                        'Saving your game spec<span class="dots">...</span></span>',
                        unsafe_allow_html=True,
                    )
                    # Retry up to 3 times until we get a tool call
                    for attempt in range(3):
                        try:
                            response = _invoke_with_fallback(messages_to_send, with_tools=True)
                        except Exception as e:
                            st.error(f"LLM error: {e}")
                            return
                        if response.tool_calls:
                            break
                        # Escalate on retry
                        messages_to_send = list(st.session_state.lc_messages) + [
                            HumanMessage(content=(
                                "URGENT: Call save_contracts tool NOW. "
                                "All information has been collected. No more questions. Tool call only."
                            ))
                        ]
                    if not response.tool_calls:
                        st.error("Could not trigger save — please type 'save' to retry.")
                        return
        else:
            # ── Normal streaming for mid-conversation messages ────────────────
            streamed_response = None
            try:
                with stream_container:
                    components.html("""<script>
                      (function() {
                        function scroll() {
                          var main = window.parent.document.querySelector('[data-testid="stMainBlockContainer"]');
                          if (main) { main.scrollTop = main.scrollHeight; return; }
                          window.parent.scrollTo(0, window.parent.document.body.scrollHeight);
                        }
                        scroll(); setTimeout(scroll, 100); setTimeout(scroll, 400);
                      })();
                    </script>""", height=0)
                    with st.chat_message("assistant", avatar=_next_avatar):
                        placeholder = st.empty()
                        placeholder.markdown(
                            '<span style="color:rgba(255,255,255,0.35);font-style:italic">'
                            'Thinking<span class="dots">...</span></span>',
                            unsafe_allow_html=True,
                        )
                        for chunk in _stream_with_fallback(messages_to_send):
                            if streamed_response is None:
                                streamed_response = chunk
                            else:
                                streamed_response = streamed_response + chunk
                            if chunk.content:
                                raw_content += chunk.content
                                placeholder.markdown(raw_content.replace(MARKER, "").strip() + " ▌")

                        display_content = raw_content.replace(MARKER, "").strip()
                        placeholder.markdown(display_content if display_content else "")

            except Exception as e:
                st.error(f"LLM error: {e}")
                return

            response = streamed_response

        if response is None:
            return

        st.session_state.lc_messages.append(response)

        # Guard: block premature saves — LLM must wait until all fields collected
        if response.tool_calls and not should_save:
            block_msg = HumanMessage(content=(
                "You called save_contracts too early. "
                f"You still need information from the user — keep the conversation going. "
                "Ask about the next missing required field in ONE short sentence."
            ))
            st.session_state.lc_messages.append(block_msg)
            try:
                redirect = _invoke_with_fallback(st.session_state.lc_messages, with_tools=False)
            except Exception as e:
                st.error(f"LLM error: {e}")
                return
            st.session_state.lc_messages.append(redirect)
            if redirect.content:
                st.session_state.chat_history.append({"role": "assistant", "content": redirect.content})
            st.rerun()
            return

        if response.tool_calls:
            for tool_call in response.tool_calls:
                if tool_call["name"] == "save_contracts":
                    try:
                        result = save_contracts.invoke(tool_call["args"])
                    except Exception as e:
                        st.error(f"Error saving contracts: {e}")
                        return
                    st.session_state.lc_messages.append(
                        ToolMessage(content=result, tool_call_id=tool_call["id"])
                    )
                    try:
                        final = _invoke_with_fallback(st.session_state.lc_messages, with_tools=False)
                        st.session_state.lc_messages.append(final)
                        st.session_state.chat_history.append({"role": "assistant", "content": final.content})
                    except Exception:
                        pass
                    st.session_state.contracts_saved = True
                    st.rerun()
        else:
            if display_content:
                st.session_state.chat_history.append({"role": "assistant", "content": display_content})
            st.rerun()

    if prompt_to_process:
        process_message(prompt_to_process)
