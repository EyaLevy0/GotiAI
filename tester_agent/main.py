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
# LangChain + MCP imports
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from mcp import StdioServerParameters

# Local tools & prompts
from tester_agent import tools as local_tools
from tester_agent.prompts import SYSTEM_PROMPT


async def _start_mcp_client(command: list[str]) -> MultiServerMCPClient:
    """Start and return a MultiServerMCPClient connected to the given command.

    The function attempts to use the asynchronous context manager API when
    available; otherwise it falls back to explicit start/stop methods if
    provided by the client implementation. The returned client must be
    closed/stopped by the caller (see `run_agent` cleanup code).
    """
    client = MultiServerMCPClient(
        server_commands=[command],
        server_parameters=StdioServerParameters(
            command=command[0],
            args=command[1:],
        ),
    )

    # Prefer async context manager style if the client supports it. We still
    # return the client object to the caller so they can explicitly stop it.
    if hasattr(client, "__aenter__"):
        # Use __aenter__ to ensure the client has started properly
        await client.__aenter__()  # type: ignore[arg-type]
        return client

    # Fallback: try a start() coroutine
    if hasattr(client, "start"):
        start_coro = getattr(client, "start")
        if asyncio.iscoroutinefunction(start_coro):
            await start_coro()  # type: ignore[arg-type]
            return client

    # If no well-known start mechanism is available, return the client and
    # let the caller attempt operations which may raise clear errors.
    return client


async def _stop_mcp_client(client: MultiServerMCPClient) -> None:
    """Stop/close the MCP client, handling multiple adapter APIs."""
    try:
        if hasattr(client, "__aexit__"):
            await client.__aexit__(None, None, None)  # type: ignore[arg-type]
            return

        if hasattr(client, "stop"):
            stop_coro = getattr(client, "stop")
            if asyncio.iscoroutinefunction(stop_coro):
                await stop_coro()  # type: ignore[arg-type]
                return

        if hasattr(client, "close"):
            close_coro = getattr(client, "close")
            if asyncio.iscoroutinefunction(close_coro):
                await close_coro()  # type: ignore[arg-type]
                return
    except Exception:
        # Best-effort cleanup; do not raise on shutdown
        return


def _collect_local_tools() -> list:
    """Return the local StructuredTool objects implemented in `tools.py`.

    We expect the functions in `tester_agent.tools` were decorated with the
    LangChain `@tool` decorator and therefore expose structured tool wrapper
    objects (with `.invoke` available). We return those wrapper objects so
    they can be passed directly to an agent creation API.
    """
    return [
        local_tools.run_godot_compiler,
        local_tools.search_godot_docs,
        local_tools.read_file,
        local_tools.overwrite_file,
    ]


async def run_agent(project_path: str) -> None:
    """Set up MCP, combine tools, create agent executor, and run it.

    This function performs:
    1. Loads environment (dotenv)
    2. Starts the MCP client and retrieves MCP tools
    3. Combines MCP tools with our local tools
    4. Creates an LLM and a tool-calling agent + executor
    5. Executes the agent with the `project_path` input
    6. Ensures the MCP client is shut down in `finally`
    """
    # Load the repository root .env to ensure shared API keys are used.
    repo_root = Path(__file__).resolve().parents[1]
    load_dotenv(dotenv_path=repo_root / ".env")

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
