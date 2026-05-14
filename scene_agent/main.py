"""Command-line entry for the Scene Agent demo.

This script retrieves Godot documentation context for a user request,
builds a system/user prompt pair, and sends it to the local LLM client.

Usage:
    python -m scene_agent.main "<your request here>"

Set the environment variable `USE_MOCK_LLM=1` to run without a live LLM.
"""

import os
import sys
from typing import Optional

from scene_agent.tools.godot_docs_tool import retrieve_godot_docs_context
from scene_agent.llm_client import ask_llm, ask_llm_mock

SYSTEM_PROMPT = (
    "You are an expert Godot developer and GDScript author. Use the provided Godot "
    "documentation context only as factual reference. Produce concise, correct, "
    "and runnable Godot code (GDScript) and a short structured summary. If the "
    'documentation does not cover a detail, say "Unknown / not in docs" rather '
    "than inventing specifics. Output must start with a JSON summary (see schema), "
    "then the code files separated and labeled."
)


def build_user_prompt(docs: str, request: str) -> str:
    return (
        f"Documentation Context:\n{docs}\n\n"
        f"User request:\n{request}\n\n"
        "Task:\n"
        "1) Produce a JSON summary with keys:\n"
        '   - "nodes": list of Godot scene nodes to create (type, name, parent)\n'
        '   - "scripts": list of { "path": "<suggested path>", "node": "<attached node>", "language": "gdscript", "code": "<full file contents as string>" }\n'
        '   - "assets": list of required assets (type, path, notes)\n'
        '   - "steps": ordered short steps to integrate the code into a Godot project\n'
        '   - "references": list of { "title": "<doc title>", "url": "<doc url>" } used from the documentation context\n\n'
        "2) After the JSON, provide the full GDScript files exactly as they should be saved (include file path labels).\n\n"
        "Constraints:\n"
        "- Target Godot docs referenced in the provided context.\n"
        "- Keep code runnable and minimal; avoid unrelated features.\n"
        '- If a value is unknown from docs, state it explicitly as "Unknown / not in docs".\n'
    )


def main(argv: Optional[list[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]

    if argv:
        request_text = " ".join(argv)
    else:
        request_text = (
            "Create a minimal 2D player controller using CharacterBody2D: walk, run, "
            "jump, gravity. Provide a JSON summary and GDScript files."
        )

    print(f"Using request: {request_text}")

    docs = retrieve_godot_docs_context(
        request_text,
        max_pages=1,
        max_total_chars=3000,
    )

    user_prompt = build_user_prompt(docs, request_text)

    use_mock = os.getenv("USE_MOCK_LLM", "0") == "1"

    try:
        if use_mock:
            print("USE_MOCK_LLM=1 -> using mock LLM client")
            response = ask_llm_mock(user_prompt)
        else:
            response = ask_llm(
                prompt=user_prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.2,
                max_tokens=400,
            )

        print("\n--- LLM RESPONSE START ---\n")
        print(response)
        print("\n--- LLM RESPONSE END ---\n")

        return 0

    except Exception as e:
        print(f"Error calling LLM: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
