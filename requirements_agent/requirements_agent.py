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

load_dotenv(override=True)

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
        "graph_state",
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


# ── Godot project bootstrap + pipeline trigger ──────────────────────────────
_GODOT_PROJECT_ICON_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128">
  <rect width="128" height="128" rx="16" fill="#478cbf"/>
  <text x="64" y="80" font-size="72" text-anchor="middle" fill="white">G</text>
</svg>
"""

_PROJECT_GODOT_TEMPLATE = """\
; Engine configuration file.
; It's best edited using the editor UI and not directly,
; since the parameters are not all documented.
;
; Format:
;   [section] ; section goes between []
;   param=value ; assign values to parameters

config_version=5

[application]

config/name="{name}"
config/features=PackedStringArray("4.3", "Forward Plus")
config/icon="res://icon.svg"
run/main_scene="res://main.tscn"

[input]

move_left={{
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":65,"key_label":0,"unicode":97,"location":0,"echo":false,"script":null)
, Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194319,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)
]
}}
move_right={{
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":68,"key_label":0,"unicode":100,"location":0,"echo":false,"script":null)
, Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194321,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)
]
}}
move_up={{
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":87,"key_label":0,"unicode":119,"location":0,"echo":false,"script":null)
, Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194320,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)
]
}}
move_down={{
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":83,"key_label":0,"unicode":115,"location":0,"echo":false,"script":null)
, Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194322,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)
]
}}
jump={{
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":32,"key_label":0,"unicode":32,"location":0,"echo":false,"script":null)
]
}}
shoot={{
"deadzone": 0.5,
"events": [Object(InputEventMouseButton,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"canceled":false,"button_index":1,"canceled_pressed":false,"double_click":false,"script":null)
, Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":74,"key_label":0,"unicode":106,"location":0,"echo":false,"script":null)
]
}}

[rendering]

renderer/rendering_method="forward_plus"
"""

_MAIN_TSCN_TEMPLATE = """\
[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://main.gd" id="1_main"]

[node name="Main" type="Node"]
script = ExtResource("1_main")
"""


def _create_godot_project(project_path: Path, game_name: str) -> None:
    """Create or repair a minimal Godot 4 project at *project_path*.

    Guarantees that Godot recognizes the directory as a runnable project:
    valid ``project.godot`` (config_version + main_scene + input map),
    a ``main.tscn`` that loads ``main.gd``, a placeholder ``main.gd``,
    and an ``icon.svg``.
    """
    project_path.mkdir(parents=True, exist_ok=True)

    godot_file = project_path / "project.godot"
    needs_rewrite = True
    if godot_file.exists():
        try:
            existing = godot_file.read_text(encoding="utf-8")
            has_config = "\nconfig_version=" in ("\n" + existing.split("[", 1)[0])
            has_main_scene = "run/main_scene" in existing
            has_input = "[input]" in existing
            needs_rewrite = not (has_config and has_main_scene and has_input)
        except Exception:
            needs_rewrite = True
    if needs_rewrite:
        godot_file.write_text(
            _PROJECT_GODOT_TEMPLATE.format(name=game_name), encoding="utf-8"
        )

    main_tscn = project_path / "main.tscn"
    if not main_tscn.exists():
        main_tscn.write_text(_MAIN_TSCN_TEMPLATE, encoding="utf-8")

    main_gd = project_path / "main.gd"
    if not main_gd.exists():
        main_gd.write_text(
            "extends Node\n\nfunc _ready() -> void:\n\tprint(\"Game booted.\")\n",
            encoding="utf-8",
        )

    icon_file = project_path / "icon.svg"
    if not icon_file.exists():
        icon_file.write_text(_GODOT_PROJECT_ICON_SVG, encoding="utf-8")


def _derive_game_name(request_contract: dict) -> str:
    import re
    mechanic = request_contract.get("game_mechanic", "") if request_contract else ""
    words = re.findall(r"[A-Za-z]+", mechanic)[:5]
    return " ".join(words).title() if words else "My Game"


def _launch_godot_game(project_path: str) -> int:
    """Launch Godot in run mode (plays the project) and return the pid.

    Raises ``FileNotFoundError`` if ``GODOT_EXECUTABLE`` does not exist.
    """
    import subprocess
    import os as _os
    godot_exe = _os.getenv("GODOT_EXECUTABLE", "godot")
    if godot_exe != "godot" and not Path(godot_exe).exists():
        raise FileNotFoundError(f"GODOT_EXECUTABLE not found: {godot_exe}")
    proc = subprocess.Popen(
        [godot_exe, "--path", project_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.pid


def _kill_godot_holding_project(project_path: str) -> list[int]:
    """Terminate any Godot process whose cmdline references *project_path*.

    Returns the list of killed pids. Silently returns an empty list when
    ``psutil`` isn't installed.
    """
    killed: list[int] = []
    try:
        import psutil  # type: ignore
    except ImportError:
        return killed

    target = str(Path(project_path)).lower().replace("\\", "/")
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if not name.startswith("godot"):
                continue
            cmd = " ".join(proc.info.get("cmdline") or []).lower().replace("\\", "/")
            if target in cmd:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except psutil.TimeoutExpired:
                    proc.kill()
                killed.append(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return killed


def _best_effort_wipe(project_root: Path) -> list[str]:
    """Best-effort removal of regeneratable files. Returns skipped paths."""
    import shutil
    skipped: list[str] = []
    if not project_root.exists():
        return skipped

    for child in project_root.iterdir():
        try:
            if child.is_dir():
                if child.name in (".godot",):
                    continue  # leave Godot's import cache to speed things up
                shutil.rmtree(child)
            else:
                child.unlink()
        except Exception:
            skipped.append(str(child.relative_to(project_root)))
    return skipped


def _run_pipeline() -> None:
    """Wipe game_project/, run the orchestrator pipeline, then open Godot."""
    import asyncio
    import os as _os
    import shutil
    import sys
    import time
    import traceback
    sys.path.insert(0, str(Path(__file__).parent.parent))

    def _log(msg: str) -> None:
        # Mirror every step to the terminal so the user can confirm progress
        # even if Streamlit's UI doesn't flush the inner status writes.
        print(f"[pipeline] {msg}", flush=True)

    request_contract = st.session_state.get("request_contract_data") or {}
    sprite_contract  = st.session_state.get("sprite_contract_data") or {}

    game_name    = _derive_game_name(request_contract)
    project_root = Path(_os.getenv("GODOT_PROJECT_PATH", "")).expanduser()
    if not project_root.parts:
        project_root = Path(__file__).parent.parent / "game_project"
    project_path_str = str(project_root)

    progress = st.empty()
    log_lines: list[str] = []

    def _ui(line: str) -> None:
        log_lines.append(line)
        progress.markdown(
            "### Generating your Godot game…\n\n" + "\n\n".join(log_lines)
        )
        _log(line.replace("**", "").replace("`", ""))
        # Yield so Streamlit actually flushes the markdown before the next
        # blocking step. Without this, asyncio.run swallows every prior write.
        time.sleep(0.05)

    try:
        _ui(f"🧹 Cleaning previous project at `{project_path_str}`…")
        killed = _kill_godot_holding_project(project_path_str)
        if killed:
            _ui(f"   ✓ Closed prior Godot process(es): {killed}")
        skipped = _best_effort_wipe(project_root)
        if skipped:
            _ui(f"   ⚠️ Could not refresh {len(skipped)} locked file(s); using overwrite path: {skipped[:5]}")
        else:
            _ui("   ✓ Removed previous project")

        _ui("📁 Creating fresh Godot project (project.godot, main.tscn, input map, icon)…")
        _create_godot_project(project_root, game_name)
        _os.environ["GODOT_PROJECT_PATH"] = project_path_str
        _ui("   ✓ Base project created")

        try:
            from orchestrator import trigger_godot_generation
        except ImportError as exc:
            _ui(f"❌ Could not import orchestrator: `{exc}`")
            st.error("Pipeline failed.")
            return

        rc = request_contract or {}
        sc = sprite_contract or {}
        user_prompt = (
            f"Game: {game_name}\n"
            f"Mechanic: {rc.get('game_mechanic', '')}\n"
            f"Enemy interaction: {rc.get('enemy_interaction', '')}\n"
            f"Player abilities: {rc.get('character_abilities', '')}\n"
            f"Start screen: {rc.get('start_screen_instructions', '')}\n"
            f"Main character: {sc.get('main_character', '')}\n"
            f"Enemies: {sc.get('enemies', '')}\n"
            f"World background: {sc.get('world_background', '')}\n"
            f"Tileset: {sc.get('tileset_environment', '')}\n"
            f"Main menu background: {sc.get('main_menu_background', '')}\n"
            f"Project path: {project_path_str}\n"
        )

        _ui("⚙️ Running pipeline: A1 → A3 (sprites) → A2 (LLM writes code, ~60s) → A4 (test)…")
        _ui("_The LLM step is the slowest. Watch the terminal window for live progress._")
        t0 = time.time()
        with st.spinner("Agents are working… (30–120 seconds)"):
            result = asyncio.run(trigger_godot_generation(user_prompt=user_prompt))
        elapsed = time.time() - t0
        pipeline_status = (
            result.get("status", "unknown") if isinstance(result, dict) else "completed"
        )
        _ui(f"   ✓ Pipeline finished in {elapsed:.1f}s (status: `{pipeline_status}`)")

        compile_result = (
            result.get("compile_result", "") if isinstance(result, dict) else ""
        )
        if compile_result and "GODOT_COMPILER_ERRORS" in compile_result:
            _ui("   ⚠️ Godot reported compile issues — opening anyway so you can inspect.")
        elif compile_result:
            _ui("   ✓ Godot compiled the project successfully")

        _ui("🚀 Launching Godot (running the project)…")
        try:
            pid = _launch_godot_game(project_path_str)
            _ui(f"   ✓ Godot launched (pid={pid})")
        except FileNotFoundError as exc:
            _ui(f"❌ {exc}")
            st.error(
                "Set `GODOT_EXECUTABLE` in `.env` to the full path of your Godot 4 binary "
                "(e.g. `C:/Godot/godot.exe`)."
            )
            return
        except Exception as exc:
            _ui(f"❌ Could not launch Godot: `{exc}`")
            st.error(traceback.format_exc())
            return

        st.success(
            f"✅ **{game_name}** is ready. Godot is opening — switch to it (Alt+Tab) "
            f"and press **F5** to play.\n\n📁 `{project_path_str}`"
        )

        if isinstance(result, dict) and result.get("generated_code"):
            with st.expander("🎬 Generated GDScript (truncated)", expanded=False):
                st.code(str(result["generated_code"])[:3000], language="gdscript")
        if compile_result:
            with st.expander("🧪 Godot compiler output", expanded=False):
                st.code(compile_result[:3000], language="text")

    except Exception as exc:
        _log(f"FATAL: {exc}")
        st.error(f"Pipeline failed: {exc}")
        st.code(traceback.format_exc())


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

        if st.button("🚀 Run Full Pipeline", type="primary", use_container_width=True):
            _run_pipeline()

        st.stop()

    stream_container = st.container()

    if st.session_state.pending_input:
        pending = st.session_state.pending_input
        st.session_state.pending_input = None
        prompt_to_process = pending
    else:
        prompt_to_process = st.chat_input("Write your answer...")

    def process_message(prompt: str):
        """Handle one complete user turn: stream response, handle tool calls."""
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        st.session_state.lc_messages.append(HumanMessage(content=prompt))

        # Run graph extraction silently to keep the stepper/progress up to date.
        try:
            updated_state = get_graph().invoke({
                **st.session_state.graph_state,
                "latest_user_message": prompt,
            })
            st.session_state.graph_state = updated_state
        except Exception:
            pass  # stepper stays as-is; conversation continues normally

        messages_to_send = list(st.session_state.lc_messages)

        # Always stream — the LLM decides when to call save_contracts.
        streamed_response = None
        raw_content = ""
        display_content = ""

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

        user_turns = sum(1 for m in st.session_state.chat_history if m["role"] == "user")

        def _save_from_args(args: dict, tool_call_id: str) -> None:
            try:
                result = save_contracts.invoke(args)
            except Exception as exc:
                st.error(f"Error saving contracts: {exc}")
                return
            st.session_state.lc_messages.append(
                ToolMessage(content=result, tool_call_id=tool_call_id)
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

        if response.tool_calls:
            for tool_call in response.tool_calls:
                if tool_call["name"] == "save_contracts":
                    if user_turns < 4:
                        block_msg = HumanMessage(content=(
                            f"You tried to save after only {user_turns} user answer(s). "
                            "You must ask about all 4 required fields first: "
                            "game mechanic, enemy interaction, character abilities, main character look. "
                            "Keep asking — do NOT call save_contracts yet."
                        ))
                        st.session_state.lc_messages.append(block_msg)
                        try:
                            redirect = invoke_with_backoff(st.session_state.lc_messages, with_tools=False)
                            st.session_state.lc_messages.append(redirect)
                            if redirect.content:
                                st.session_state.chat_history.append({"role": "assistant", "content": redirect.content})
                        except Exception:
                            pass
                        st.rerun()
                        return
                    _save_from_args(tool_call["args"], tool_call["id"])
                    return

        # Fallback: model wrote a JSON tool call in plain text instead of using
        # the tool-calling API. Detect formats like:
        #   {"name": "save_contracts", "parameters": {...}}
        if display_content and "save_contracts" in display_content:
            import json as _json
            args: dict | None = None
            # Walk every '{' and try to parse a balanced JSON object starting there.
            text = display_content
            for start in range(len(text)):
                if text[start] != "{":
                    continue
                depth = 0
                in_str = False
                esc = False
                for end in range(start, len(text)):
                    c = text[end]
                    if esc:
                        esc = False
                        continue
                    if c == "\\" and in_str:
                        esc = True
                        continue
                    if c == '"':
                        in_str = not in_str
                        continue
                    if in_str:
                        continue
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            candidate = text[start : end + 1]
                            try:
                                obj = _json.loads(candidate)
                            except Exception:
                                break
                            if (
                                isinstance(obj, dict)
                                and obj.get("name") == "save_contracts"
                            ):
                                p = (
                                    obj.get("parameters")
                                    or obj.get("arguments")
                                    or obj.get("args")
                                )
                                if isinstance(p, dict):
                                    args = p
                            break
                if args is not None:
                    break
            if args is not None:
                st.session_state.chat_history.append(
                    {"role": "assistant", "content": "Got it — saving your game spec now…"}
                )
                _save_from_args(args, "fallback-json")
                return

        if display_content:
            st.session_state.chat_history.append(
                {"role": "assistant", "content": display_content}
            )
        st.rerun()

    if prompt_to_process:
        process_message(prompt_to_process)
