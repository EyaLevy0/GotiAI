import asyncio
import sys
from pathlib import Path

# Ensure the repository root is on sys.path when running this script directly.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import orchestrator


async def fake_run_tester_agent(project_path: str) -> None:
    """Simulate the tester agent without launching external MCP or LLMs."""
    # Quick no-op to simulate processing time
    await asyncio.sleep(0)


async def main_test() -> None:
    # Patch the imported run_tester_agent used by the orchestrator
    orchestrator.run_tester_agent = fake_run_tester_agent

    final = await orchestrator.trigger_godot_generation("smoke-prompt")

    assert final.get("user_prompt") == "smoke-prompt"
    # The sequential graph sets this status on completion of A4
    assert final.get("status") == "A4_tester_completed"
    print("orchestrator smoke test: PASSED")


if __name__ == "__main__":
    asyncio.run(main_test())
