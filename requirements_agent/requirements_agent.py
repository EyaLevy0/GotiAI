"""GameForge AI — Streamlit entry point.

Handles all UI rendering, session management, and message processing.
The LangGraph graph (graph.py) drives field extraction and phase routing;
this module owns streaming, saving, and visual presentation.
"""

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from pathlib import Path

from graph import build_graph
from llm import invoke_with_backoff, stream_with_backoff
from prompts import CHECKLIST_FIELDS, OPTIONAL_INDICES, REQUIRED_INDICES, build_system_prompt
from state import FIELD_KEYS
from tools import AGENT_DATA_PATH, save_contracts

load_dotenv()

# ---------------------------------------------------------------------------
# Icon
# ---------------------------------------------------------------------------
ICON_PATH = Path(__file__).parent / "assets" / "gameforge_icon.png"


def _load_icon():
    """Load the app icon as a PIL Image, falling back to an emoji string."""
    if ICON_PATH.exists():
        try:
            from PIL import Image
            return Image.open(ICON_PATH)
        except Exception:
            pass
    return "🎮"


_ICON_IMAGE = _load_icon()

# ---------------------------------------------------------------------------
# Page config  (must be the first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="GameForge AI",
    page_icon=str(ICON_PATH) if ICON_PATH.exists() else "🎮",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Graph (cached so the compiled graph is built once per process)
# ---------------------------------------------------------------------------
@st.cache_resource
def get_graph():
    """Build and cache the LangGraph extraction graph."""
    return build_graph()


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------
def _initial_graph_state(active_indices: list) -> dict:
    """Return a fresh graph state dict with all fields set to None.

    Args:
        active_indices: List of int indices that are active for this session.

    Returns:
        A fully initialised GameDesignState-compatible dict.
    """
    return {
        **{key: None for key in FIELD_KEYS},
        "active_indices": active_indices,
        "phase": "gathering",
        "current_question_field": FIELD_KEYS[0],
        "latest_user_message": "",
    }


def reset_session():
    """Clear all session state keys and trigger a full page rerun."""
    for key in [
        "lc_messages", "chat_history", "contracts_saved", "pending_input",
        "request_contract_data", "sprite_contract_data", "enabled_optional",
        "graph_state", "last_processed_input",
    ]:
        st.session_state.pop(key, None)
    st.rerun()


def init_session():
    """Initialise session state on the first run of this Streamlit session."""
    if "lc_messages" not in st.session_state:
        active = sorted(REQUIRED_INDICES)
        st.session_state.lc_messages           = [SystemMessage(content=build_system_prompt(REQUIRED_INDICES))]
        st.session_state.chat_history          = []
        st.session_state.contracts_saved       = False
        st.session_state.pending_input         = None
        st.session_state.request_contract_data = None
        st.session_state.sprite_contract_data  = None
        st.session_state.enabled_optional      = set()
        st.session_state.graph_state           = _initial_graph_state(active)
        greeting = (
            "Welcome to **GameForge AI**!\n\n"
            "I'll help you design your 2D Godot game and generate the full spec files automatically.\n\n"
            "**What kind of 2D game do you want to make?**\n"
            "*(e.g. platformer, top-down shooter, endless runner, puzzle)*"
        )
        st.session_state.chat_history.append({"role": "assistant", "content": greeting})

    if "enabled_optional" not in st.session_state:
        st.session_state.enabled_optional = set()

    if "graph_state" not in st.session_state:
        active = sorted(REQUIRED_INDICES | st.session_state.enabled_optional)
        st.session_state.graph_state = _initial_graph_state(active)


init_session()

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=Inter:wght@400;500;600&display=swap');

  * { box-sizing: border-box; }

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

  [data-testid="stHeader"]  { background: transparent !important; }
  [data-testid="stToolbar"] { display: none; }
  #MainMenu { display: none; }
  [data-testid="stDecoration"] { display: none; }
  [data-testid="stSidebar"]                { display: none !important; }
  [data-testid="stSidebarCollapsedControl"]{ display: none !important; }

  [data-testid="stHorizontalBlock"] > [data-testid="column"]:first-child {
      align-self: flex-start !important;
      position: sticky !important;
      top: 1rem !important;
  }

  .left-panel {
      background: rgba(6, 4, 22, 0.7);
      backdrop-filter: blur(24px) saturate(160%);
      border-right: 1px solid rgba(123,47,255,0.2);
      border-radius: 16px;
      padding: 1.4rem 1.2rem;
  }

  .sb-brand {
      font-family: 'Orbitron', sans-serif;
      font-size: 1.1rem; font-weight: 900;
      letter-spacing: 1px; color: #fff;
      padding: 0.4rem 0 1.2rem;
      border-bottom: 1px solid rgba(123,47,255,0.25);
      margin-bottom: 1rem;
  }
  .sb-brand .accent { color: #7df9ff; }

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
      color: #fff; box-shadow: 0 0 14px rgba(123,47,255,0.7);
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

  .options-label {
      font-family: 'Inter', sans-serif;
      font-size: 0.7rem; color: rgba(255,255,255,0.35);
      letter-spacing: 2px; text-transform: uppercase;
      margin: 1.2rem 0 0.5rem;
  }

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

  [data-testid="stMainBlockContainer"] {
      background: rgba(4, 5, 20, 0.5) !important;
      backdrop-filter: blur(18px) saturate(120%) !important;
      border-left: 1px solid rgba(123,47,255,0.1);
      min-height: 100vh; position: relative; z-index: 10;
  }

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
      font-size: 2.1rem; font-weight: 900; margin: 0 0 0.4rem;
      background: linear-gradient(100deg, #fff 0%, #a78bfa 50%, #7df9ff 100%);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      animation: glow-text 4s ease-in-out infinite alternate;
  }
  @keyframes glow-text {
      from { filter: brightness(1); }
      to   { filter: brightness(1.2) drop-shadow(0 0 10px #7b2fff55); }
  }
  .hero p { font-family: 'Inter', sans-serif; font-size: 0.87rem; color: rgba(255,255,255,0.45); margin: 0; }

  .px { display: inline-block; width: 7px; height: 7px; border-radius: 2px; margin-right: 7px; }
  .px.a { background:#7b2fff; animation: floatPx 3s ease-in-out infinite alternate; }
  .px.b { background:#7df9ff; animation: floatPx 3s ease-in-out infinite alternate; animation-delay:.7s; }
  .px.c { background:#a78bfa; animation: floatPx 3s ease-in-out infinite alternate; animation-delay:1.4s; }
  @keyframes floatPx { from { transform: translateY(0) rotate(0deg); } to { transform: translateY(-8px) rotate(18deg); } }

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

  [data-testid="stBottom"],
  [data-testid="stBottom"] > div,
  [data-testid="stBottom"] > div > div {
      background: rgba(4, 5, 20, 0.88) !important;
      backdrop-filter: blur(20px) !important;
      border-top: 1px solid rgba(123,47,255,0.2) !important;
      box-shadow: 0 -6px 30px rgba(80,0,200,0.12) !important;
  }

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

  .dots { display: inline-block; }
  @keyframes blink { 0%,100% { opacity: 0.2; } 50% { opacity: 1; } }
  .dots { animation: blink 1.2s ease-in-out infinite; }

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
# Emoji rain (plays once on contract save)
# ---------------------------------------------------------------------------
def emoji_rain():
    """Inject a full-screen emoji rain animation via an iframe."""
    components.html("""
    <style>
      #rain-container {
        position: fixed; top: 0; left: 0;
        width: 100vw; height: 100vh;
        pointer-events: none; z-index: 99999; overflow: hidden;
      }
      .emoji-drop {
        position: absolute; top: -80px; font-size: 2rem;
        animation: fall linear forwards; user-select: none;
      }
      @keyframes fall {
        0%   { transform: translateY(0) rotate(0deg);        opacity: 1; }
        80%  { opacity: 1; }
        100% { transform: translateY(110vh) rotate(360deg);  opacity: 0; }
      }
    </style>
    <div id="rain-container"></div>
    <script>
      const emojis = ["🤖","👾","👽","🧟","🚀","🎮","💥","🛸","⚡","🔫","🧠","🪐"];
      const container = document.getElementById("rain-container");
      for (let i = 0; i < 60; i++) {
        const el = document.createElement("span");
        el.className   = "emoji-drop";
        el.textContent = emojis[Math.floor(Math.random() * emojis.length)];
        el.style.left             = `${Math.random() * 100}vw`;
        el.style.animationDelay   = `${Math.random() * 3}s`;
        el.style.animationDuration= `${2 + Math.random() * 3}s`;
        el.style.fontSize         = `${1.2 + Math.random() * 1.8}rem`;
        container.appendChild(el);
      }
      setTimeout(() => container.remove(), 7000);
    </script>
    """, height=0)


# ---------------------------------------------------------------------------
# Auto-scroll — fires on every rerun so the latest message stays visible
# ---------------------------------------------------------------------------
components.html("""
<script>
  (function() {
    function scrollToBottom() {
      var main = window.parent.document.querySelector('[data-testid="stMainBlockContainer"]');
      if (main) { main.scrollTop = main.scrollHeight; }
      else { window.parent.scrollTo(0, window.parent.document.body.scrollHeight); }
    }
    scrollToBottom();
    setTimeout(scrollToBottom, 150);
    setTimeout(scrollToBottom, 500);
  })();
</script>
""", height=0)

# ---------------------------------------------------------------------------
# Derived state
# ---------------------------------------------------------------------------
active_indices = sorted(REQUIRED_INDICES | st.session_state.enabled_optional)
total_active   = len(active_indices)
graph_state    = st.session_state.graph_state
active_keys    = [FIELD_KEYS[i] for i in active_indices]
completed      = sum(1 for key in active_keys if graph_state.get(key))
progress_pct   = min(int((completed / total_active) * 100), 100) if total_active else 0

# ---------------------------------------------------------------------------
# Layout
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

    stepper_html = '<div class="stepper">'
    for step_num, field_idx in enumerate(active_indices):
        label  = CHECKLIST_FIELDS[field_idx][1]
        is_req = field_idx in REQUIRED_INDICES
        badge  = "" if is_req else '<span style="font-size:0.6rem;opacity:0.5;margin-left:4px">opt</span>'
        field_key = FIELD_KEYS[field_idx]
        if graph_state.get(field_key):
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

    st.markdown('<div class="options-label" style="margin-top:1.2rem">Optional fields</div>', unsafe_allow_html=True)
    for field_idx in sorted(OPTIONAL_INDICES):
        label   = CHECKLIST_FIELDS[field_idx][1]
        enabled = field_idx in st.session_state.enabled_optional
        if st.button(
            f"✓ {label}" if enabled else f"＋ {label}",
            key=f"opt_toggle_{field_idx}",
            use_container_width=True,
            type="primary" if enabled else "secondary",
        ):
            if enabled:
                st.session_state.enabled_optional.discard(field_idx)
            else:
                st.session_state.enabled_optional.add(field_idx)
            new_active = REQUIRED_INDICES | st.session_state.enabled_optional
            st.session_state.lc_messages[0] = SystemMessage(content=build_system_prompt(new_active))
            st.session_state.graph_state["active_indices"] = sorted(new_active)
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("↺ Start over", key="reset_btn", use_container_width=True):
        reset_session()

    st.markdown('</div>', unsafe_allow_html=True)

# ── Right panel ──────────────────────────────────────────────────────────────
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
        if msg["role"] == "assistant":
            with st.chat_message("assistant", avatar=_ICON_IMAGE):
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

    stream_container = st.container()

    # Prevent infinite loops: track the last processed input to avoid reprocessing on Streamlit reruns
    if "last_processed_input" not in st.session_state:
        st.session_state.last_processed_input = None

    if st.session_state.pending_input:
        pending = st.session_state.pending_input
        st.session_state.pending_input = None
        prompt_to_process = pending
    else:
        prompt_to_process = st.chat_input("Write your answer...")

    def _build_force_message(n_fields: int) -> str:
        """Return the enrichment instruction injected before the save call.

        Args:
            n_fields: Number of active fields collected.

        Returns:
            A prompt string instructing the LLM to expand all fields and call save_contracts.
        """
        return (
            f"You now have answers for all {n_fields} required fields. "
            "Call save_contracts NOW. For EVERY field, write rich expanded Godot specs — "
            "do NOT copy the user's words verbatim. Expand into full technical detail:\n"
            "• game_mechanic: Camera2D mode + smoothing, gravity px/s², world width px, "
            "HUD elements with screen positions, win/lose conditions, level structure\n"
            "• enemy_interaction: collision shape + exact px size, damage amount + type, "
            "knockback force, patrol range px, aggro radius px, defeat method, score, drops\n"
            "• character_abilities: walk px/s, run px/s, jump_velocity px/s, max jump height px, "
            "all animation states with frame counts (idle:4f run:8f jump:3f fall:2f hurt:2f death:4f), "
            "coyote_time ms, jump_buffer ms, special ability cooldowns\n"
            "• main_character: sprite size px, full color palette with 4-5 hex codes and roles, "
            "spritesheet layout, shader effects, particle effects\n"
            "• All visual fields: sprite sizes, hex palettes, frame counts, animations\n"
            "For any field the user did NOT answer — invent smart, coherent defaults. "
            "Every field must be 4-6 sentences of dense detail. No empty strings."
        )

    def process_message(prompt: str):
        """Handle one complete user turn: extract, route, then stream or save.

        Args:
            prompt: The raw text the user submitted.
        """
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        st.session_state.lc_messages.append(HumanMessage(content=prompt))

        # Run LangGraph: extract fields from this message and determine phase.
        updated_state = get_graph().invoke({
            **st.session_state.graph_state,
            "latest_user_message": prompt,
        })
        st.session_state.graph_state = updated_state
        should_save = updated_state.get("phase") == "saving"

        messages_to_send = list(st.session_state.lc_messages)
        if should_save:
            messages_to_send.append(HumanMessage(content=_build_force_message(total_active)))

        response        = None
        raw_content     = ""
        display_content = ""

        if should_save:
            with stream_container:
                with st.chat_message("assistant", avatar=_ICON_IMAGE):
                    placeholder = st.empty()
                    placeholder.markdown(
                        '<span style="color:rgba(255,255,255,0.35);font-style:italic">'
                        'Saving your game spec<span class="dots">...</span></span>',
                        unsafe_allow_html=True,
                    )
                    for attempt in range(3):
                        try:
                            response = invoke_with_backoff(messages_to_send, with_tools=True)
                        except Exception as exc:
                            st.error(f"LLM error: {exc}")
                            return
                        if response.tool_calls:
                            break
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
            streamed_response = None
            try:
                with stream_container:
                    with st.chat_message("assistant", avatar=_ICON_IMAGE):
                        placeholder = st.empty()
                        placeholder.markdown(
                            '<span style="color:rgba(255,255,255,0.35);font-style:italic">'
                            'Thinking<span class="dots">...</span></span>',
                            unsafe_allow_html=True,
                        )
                        for chunk in stream_with_backoff(messages_to_send):
                            if streamed_response is None:
                                streamed_response = chunk
                            else:
                                streamed_response = streamed_response + chunk
                            if chunk.content:
                                raw_content += chunk.content
                                placeholder.markdown(raw_content.strip() + " ▌")

                        display_content = raw_content.strip()
                        placeholder.markdown(display_content if display_content else "")

            except Exception as exc:
                st.error(f"LLM error: {exc}")
                return

            response = streamed_response

        if response is None:
            return

        st.session_state.lc_messages.append(response)

        # Guard: block premature saves if the graph phase changed between turns.
        if response.tool_calls and not should_save:
            block_msg = HumanMessage(content=(
                "You called save_contracts too early. "
                "Keep the conversation going and ask about the next missing field."
            ))
            st.session_state.lc_messages.append(block_msg)
            try:
                redirect = invoke_with_backoff(st.session_state.lc_messages, with_tools=False)
            except Exception as exc:
                st.error(f"LLM error: {exc}")
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
                    except Exception as exc:
                        st.error(f"Error saving contracts: {exc}")
                        return
                    st.session_state.lc_messages.append(
                        ToolMessage(content=result, tool_call_id=tool_call["id"])
                    )
                    try:
                        final = invoke_with_backoff(st.session_state.lc_messages, with_tools=False)
                        st.session_state.lc_messages.append(final)
                        st.session_state.chat_history.append(
                            {"role": "assistant", "content": final.content}
                        )
                    except Exception:
                        pass
                    st.session_state.contracts_saved = True
                    st.rerun()
        else:
            if display_content:
                st.session_state.chat_history.append(
                    {"role": "assistant", "content": display_content}
                )
            st.rerun()

    if prompt_to_process and prompt_to_process != st.session_state.last_processed_input:
        st.session_state.last_processed_input = prompt_to_process
        process_message(prompt_to_process)

