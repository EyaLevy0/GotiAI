"""Tester Agent (A4) — compiles the Godot project directly, no LLM/MCP needed."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from dotenv import load_dotenv

from tester_agent.tools import run_godot_compiler


async def run_agent(project_path: str) -> None:
    """Run Godot compiler headlessly and print the result."""
    load_dotenv(override=True)

    result = run_godot_compiler.invoke({"project_path": project_path})
    print("COMPILE_RESULT:", result)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Tester Agent")
    parser.add_argument("project_path", help="Path to the Godot project root")
    args = parser.parse_args()

    try:
        asyncio.run(run_agent(str(Path(args.project_path))))
        return 0
    except KeyboardInterrupt:
        return 2
    except Exception as exc:
        print("Agent failed:", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
