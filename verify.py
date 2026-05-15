"""Quick connectivity check for all agents in the pipeline.

Run with:  python verify.py [godot_project_path]

If no project path is given, a minimal Godot project is created in a temp
directory for the tester-agent test.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


def _header(title: str) -> None:
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"{'='*55}")


# ---------------------------------------------------------------------------
# A1 — read contracts
# ---------------------------------------------------------------------------

def check_a1() -> bool:
    _header("A1 — Manager: read contracts")
    agent_data = Path(__file__).parent / "requirements_agent" / "agent_data"
    req = agent_data / "request_manager_contract.json"
    spr = agent_data / "sprite_generation_contract.json"

    if not req.exists():
        print(f"  {FAIL}  request_manager_contract.json not found")
        print("         Run the requirements_agent Streamlit app first.")
        return False

    contract = json.loads(req.read_text(encoding="utf-8"))
    print(f"  {PASS}  request_manager_contract.json loaded")
    print(f"         project_path = {contract.get('project_directory_path', '(none)')}")

    if spr.exists():
        print(f"  {PASS}  sprite_generation_contract.json found")
    else:
        print(f"  WARN   sprite_generation_contract.json not found (optional)")

    return True


# ---------------------------------------------------------------------------
# A2 — scene_agent
# ---------------------------------------------------------------------------

def check_a2() -> bool:
    _header("A2 — Scene Agent (Groq)")
    try:
        from scene_agent.llm_client import ask_llm
        result = ask_llm("Reply with only the word OK.", max_tokens=5)
        print(f"  {PASS}  scene_agent LLM responded: {result.strip()!r}")
        return True
    except Exception as exc:
        print(f"  {FAIL}  {exc}")
        return False


# ---------------------------------------------------------------------------
# A4 — tester_agent (compile-only, no MCP)
# ---------------------------------------------------------------------------

def _make_minimal_godot_project(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "project.godot").write_text(
        '[gd_resource type="ProjectSettings"]\n\n[application]\nconfig/name="VerifyTest"\n',
        encoding="utf-8",
    )


def check_a4(project_path: str | None) -> bool:
    _header("A4 — Tester Agent (Godot compile check)")
    try:
        from tester_agent.tools import run_godot_compiler
    except Exception as exc:
        print(f"  {FAIL}  import error: {exc}")
        return False

    if project_path:
        p = Path(project_path)
    else:
        tmp = Path(tempfile.mkdtemp()) / "godot_verify"
        _make_minimal_godot_project(tmp)
        p = tmp
        print(f"  INFO   created temp project at {p}")

    result = run_godot_compiler.invoke({"project_path": str(p)})
    if result.startswith("GODOT_EXECUTABLE_NOT_FOUND"):
        print(f"  {FAIL}  Godot not found in PATH")
        return False
    if result.startswith("INVALID_PROJECT_PATH"):
        print(f"  {FAIL}  {result}")
        return False

    print(f"  {PASS}  compiler ran — result: {result[:80]!r}")
    return True


# ---------------------------------------------------------------------------
# Full orchestrator import
# ---------------------------------------------------------------------------

def check_orchestrator() -> bool:
    _header("Orchestrator — import check")
    try:
        from orchestrator import trigger_godot_generation  # noqa: F401
        print(f"  {PASS}  orchestrator imports cleanly")
        return True
    except Exception as exc:
        print(f"  {FAIL}  {exc}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    project_path = sys.argv[1] if len(sys.argv) > 1 else None

    results = [
        check_a1(),
        check_a2(),
        check_a4(project_path),
        check_orchestrator(),
    ]

    _header("Summary")
    labels = ["A1 contracts", "A2 scene/Groq", "A4 Godot compile", "Orchestrator import"]
    all_ok = True
    for label, ok in zip(labels, results):
        status = PASS if ok else FAIL
        print(f"  {status}  {label}")
        if not ok:
            all_ok = False

    print()
    if all_ok:
        print("All checks passed — ready to run the full orchestrator.")
    else:
        print("Fix the failures above, then re-run verify.py.")

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
