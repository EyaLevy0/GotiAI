"""
Configuration settings for the Scene Agent.

This file stores shared constants such as:
- local model URL
- model name
- server port
- Godot project path
"""

import os

# Local LLM server configuration
# This points to the Podman AI Lab OpenAI-compatible API endpoint.
MODEL_BASE_URL = os.getenv(
    "MODEL_BASE_URL",
    "http://localhost:61451/v1",
)

# Exact model ID returned by:
# curl http://localhost:52546/v1/models
MODEL_NAME = os.getenv(
    "MODEL_NAME",
    "ibm-research/granite-3.2-8b-instruct-GGUF",
)


# Scene Agent server configuration
SERVER_HOST = os.getenv(
    "SERVER_HOST",
    "127.0.0.1",
)

SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))


# Optional local Godot project path
GODOT_PROJECT_PATH = os.getenv(
    "GODOT_PROJECT_PATH",
    "",
)


# LLM request timeout
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "180"))
