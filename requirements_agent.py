import json
from pathlib import Path
from typing import List

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from models import RequestManagerContract, SpriteGenerationContract

load_dotenv()

AGENT_DATA_PATH = Path(__file__).parent / "agent_data"

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
SYSTEM_PROMPT = """You are a senior game designer and Godot developer helping users plan their 2D Godot game.

Your goal is to have a natural conversation to gather the following information from the user:
  1. Game mechanic — the core game loop (e.g., "2D side-scroller like Mario", "top-down shooter")
  2. Enemy interaction — how enemies affect the player (e.g., "player takes damage on touch")
  3. Start screen — title style, buttons, any special effects
  4. Character abilities — what the player can do (e.g., run, jump, double jump, shoot)
  5. Main character visuals — appearance, colors, size
  6. Enemy visuals — what each enemy looks like
  7. World background — what the static background looks like (sky, city, forest, etc.)
  8. Ground/platforms (tileset) — what the surfaces and platforms look like
  9. Main menu background — the visual scene behind the start screen

Conversation guidelines:
- Ask exactly ONE question at a time, never more.
- Ask follow-up questions to get specific visual details when needed.
- Be encouraging and suggest creative ideas when the user is unsure.
- All visuals must fit a "2D pixel art, retro 16-bit style, flat colors, clean background" aesthetic.

--- ENRICHMENT STEP (critical) ---
Before calling save_contracts, you MUST enrich every field with professional game development details
that the user did NOT explicitly mention but are required to build a real game.

For game_mechanic, always include:
- Camera behavior, world boundaries, gravity feel, progression, HUD elements

For enemy_interaction, always include:
- Exact collision behavior, player death handling, enemy movement pattern, defeat conditions

For character_abilities, always include:
- Movement speed, jump height and feel, animation state names, cooldowns

For all visual fields, always include:
- Pixel dimensions, color palette (2-4 colors), animation frames, special effects

Do NOT ask the user about these technical details — infer them from the genre and bake them in.

Start by greeting the user warmly and asking them to describe their game idea."""

CHECKLIST_FIELDS = [
    ("game_mechanic",           "Game mechanic"),
    ("enemy_interaction",       "Enemy interaction"),
    ("start_screen",            "Start screen"),
    ("character_abilities",     "Character abilities"),
    ("main_character",          "Main character look"),
    ("enemies",                 "Enemy look"),
    ("world_background",        "World background"),
    ("tileset_environment",     "Ground & platforms"),
    ("main_menu_background",    "Main menu background"),
]

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
    start_screen_instructions: str,
    character_abilities: str,
    main_character: str,
    enemies: str,
    world_background: str,
    tileset_environment: str,
    main_menu_background: str,
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
# LLM
# ---------------------------------------------------------------------------
def get_llm():
    # Swap comments to switch provider:
    # return ChatGoogleGenerativeAI(model="gemini-2.0-flash", system_instruction=SYSTEM_PROMPT).bind_tools([save_contracts])
    return ChatOllama(model="qwen2.5:7b").bind_tools([save_contracts])

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def init_session():
    if "lc_messages" not in st.session_state:
        st.session_state.lc_messages          = [SystemMessage(content=SYSTEM_PROMPT)]
        st.session_state.chat_history         = []
        st.session_state.contracts_saved      = False
        st.session_state.pending_input        = None
        st.session_state.request_contract_data  = None
        st.session_state.sprite_contract_data   = None

        greeting = get_llm().invoke(st.session_state.lc_messages + [HumanMessage(content="Hello")])
        st.session_state.lc_messages.append(greeting)
        st.session_state.chat_history.append({"role": "assistant", "content": greeting.content})

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

  /* Checklist rows */
  .check-row {
      font-family: 'Inter', sans-serif;
      display: flex; align-items: center; gap: 10px;
      padding: 7px 0; font-size: 0.82rem;
      border-bottom: 1px solid rgba(255,255,255,0.04);
  }
  .check-row.done    { color: #4ade80; }
  .check-row.active  { color: #fff; font-weight: 600; }
  .check-row.pending { color: rgba(255,255,255,0.3); }
  .check-icon {
      width: 20px; height: 20px; border-radius: 6px;
      display: flex; align-items: center; justify-content: center;
      font-size: 0.7rem; font-weight: 700; flex-shrink: 0;
  }
  .check-icon.done    { background: #4ade8022; color: #4ade80; border: 1px solid #4ade8055; }
  .check-icon.active  { background: #7b2fff; color: #fff; box-shadow: 0 0 10px #7b2fff88; }
  .check-icon.pending { background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.25); }

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
answered     = len([m for m in st.session_state.chat_history if m["role"] == "user"])
total_fields = len(CHECKLIST_FIELDS)
progress_pct = min(int((answered / total_fields) * 100), 100)
current_step = min(answered, total_fields - 1)

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
      <div class="pbar-labels"><span>Progress</span><span>{answered} / {total_fields}</span></div>
      <div class="pbar-bg"><div class="pbar-fill" style="width:{progress_pct}%"></div></div>
    </div>
    """, unsafe_allow_html=True)

    for i, (_, label) in enumerate(CHECKLIST_FIELDS):
        if i < answered:
            css, icon = "done", "✓"
        elif i == answered:
            css, icon = "active", "▶"
        else:
            css, icon = "pending", str(i + 1)
        st.markdown(f"""
        <div class="check-row {css}">
          <div class="check-icon {css}">{icon}</div>{label}
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if not st.session_state.contracts_saved and current_step in STEP_OPTIONS:
        st.markdown('<div class="options-label">Quick pick</div>', unsafe_allow_html=True)
        for i, option in enumerate(STEP_OPTIONS[current_step]):
            if st.button(option, key=f"opt_{current_step}_{i}", use_container_width=True):
                st.session_state.pending_input = option
                st.rerun()

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

    for msg in st.session_state.chat_history:
        avatar = "🤖" if msg["role"] == "assistant" else "👾"
        with st.chat_message(msg["role"], avatar=avatar):
            st.write(msg["content"])

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

    def process_message(prompt: str):
        with st.chat_message("user", avatar="👾"):
            st.write(prompt)
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        st.session_state.lc_messages.append(HumanMessage(content=prompt))

        response = get_llm().invoke(st.session_state.lc_messages)
        st.session_state.lc_messages.append(response)

        if response.tool_calls:
            for tool_call in response.tool_calls:
                if tool_call["name"] == "save_contracts":
                    result = save_contracts.invoke(tool_call["args"])
                    st.session_state.lc_messages.append(
                        ToolMessage(content=result, tool_call_id=tool_call["id"])
                    )
                    final = get_llm().invoke(st.session_state.lc_messages)
                    st.session_state.lc_messages.append(final)
                    st.session_state.chat_history.append({"role": "assistant", "content": final.content})
                    st.session_state.contracts_saved = True
                    st.rerun()
        else:
            with st.chat_message("assistant", avatar="🤖"):
                st.write(response.content)
            st.session_state.chat_history.append({"role": "assistant", "content": response.content})
            st.rerun()

    if st.session_state.pending_input:
        pending = st.session_state.pending_input
        st.session_state.pending_input = None
        process_message(pending)

    if prompt := st.chat_input("Write your answer..."):
        process_message(prompt)
