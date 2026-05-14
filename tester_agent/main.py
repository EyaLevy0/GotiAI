"""Async MCP-enabled agent runner for the Tester Agent.

This module starts an async event loop, connects to a Godot MCP server (via
`npx -y @coding-solo/godot-mcp@latest`), collects MCP-provided tools, combines
them with local tools implemented in `tester_agent.tools`, constructs a
tool-calling agent using `ChatOpenAI`, and runs the agent executor against a
`project_path` input.

The implementation is defensive and includes fallbacks for small API
variations across LangChain / MCP adapter versions. It documents assumptions
and performs graceful cleanup of the MCP client.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Iterable
from pathlib import Path

from dotenv import load_dotenv

# LangChain + MCP imports
from langchain.chat_models import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
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
        server_commands=[command], server_parameters=StdioServerParameters()
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
    load_dotenv()

    # Resolve the MCP server command. We intentionally use `npx` to ensure the
    # MCP server can be launched without a prior install step.
    mcp_command = ["npx", "-y", "@coding-solo/godot-mcp@latest"]

    client: MultiServerMCPClient | None = None
    try:
        # Start the MCP client and obtain MCP-provided tools.
        client = await _start_mcp_client(mcp_command)

        # `get_tools` is typically an async method returning a list of Tool
        # objects that can be passed to LangChain agents. Use runtime-safe
        # checks to support slight API variations.
        if hasattr(client, "get_tools"):
            get_tools_fn = getattr(client, "get_tools")
            mcp_tools = await get_tools_fn()
        else:
            mcp_tools = []

        # Combine MCP tools with the local tools implemented in this package.
        tools: list = []
        if isinstance(mcp_tools, list):
            tools.extend(mcp_tools)
        else:
            # If an object (single toolkit) is returned, try to iterate
            try:
                tools.extend(list(mcp_tools))
            except Exception:
                pass

        tools.extend(_collect_local_tools())

        # Create the LLM. This example uses ChatOpenAI configured as requested.
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

        # Create a tool-calling agent. `create_tool_calling_agent` constructs
        # an agent specialization that uses the supplied system prompt and
        # tools. Different LangChain versions may accept slightly different
        # parameter names; this call follows the commonly available signature.
        agent = create_tool_calling_agent(llm=llm, tools=tools, system_message=SYSTEM_PROMPT)

        # Wrap the agent with an AgentExecutor to run it. Prefer async run
        # methods when available.
        executor = AgentExecutor.from_agent_and_tools(agent=agent, tools=tools, verbose=True)

        # Execute the agent with an explicit instruction to perform the
        # compile-first ReAct loop defined by the system prompt. Prefer
        # async executor methods when available.
        async def run_react_loop(executor_obj, project_path_str: str):
            instruction = (
                "Execute the STRICT compile-first ReAct loop exactly as the system "
                "prompt dictates. The project path is provided below. Follow the "
                "CALL TOOL / TOOL RESULT reporting format and stop only on SUCCESS "
                "or after 5 iterations.\n\n"
                f"PROJECT_PATH: {project_path}\n"
            )

            if hasattr(executor_obj, "arun"):
                return await executor_obj.arun(instruction)
            if hasattr(executor_obj, "aexecute"):
                return await executor_obj.aexecute(instruction)

            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, executor_obj.run, instruction)

        result = await run_react_loop(executor, project_path)
        print("AGENT_RESULT:\n", result)

    finally:
        # Ensure the MCP client is shut down even if the agent raised.
        if client is not None:
            await _stop_mcp_client(client)


def _build_cli_parser() -> argparse.ArgumentParser:
    import argparse

    parser = argparse.ArgumentParser(description="Run the Tester Agent (MCP-enabled)")
    parser.add_argument("project_path", help="Path to the Godot project root")
    return parser


def main() -> int:
    """Synchronous CLI entry that launches the async agent runner."""
    parser = _build_cli_parser()
    args = parser.parse_args()
    project_path = str(Path(args.project_path))

    try:
        asyncio.run(run_agent(project_path))
        return 0
    except KeyboardInterrupt:
        print("Interrupted by user")
        return 2
    except Exception as exc:
        print("Agent failed:", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
