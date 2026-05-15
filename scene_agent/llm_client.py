# Local LLM client. This file will handle communication with the AI model running locally through Podman AI Lab.
"""
LLM client for the Scene Agent.

Uses Groq (cloud) when GROQ_API_KEY is set, otherwise falls back to a
local OpenAI-compatible server (Podman AI Lab / Ollama).
"""

import os
from typing import Optional

import requests
from dotenv import load_dotenv

from scene_agent.config.settings import (
    MODEL_BASE_URL,
    MODEL_NAME,
    LLM_TIMEOUT_SECONDS,
)

load_dotenv(override=True)

_GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_GROQ_MODEL = "llama-3.1-8b-instant"


def ask_llm(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1000,
) -> str:
    """Send a prompt to the LLM and return the generated response text.

    Prefers Groq when GROQ_API_KEY is present; falls back to the local server.
    """

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    if _GROQ_API_KEY:
        base_url = _GROQ_BASE_URL
        model = _GROQ_MODEL
        headers = {
            "Authorization": f"Bearer {_GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        print(f"[scene_agent] Using Groq ({model})")
    else:
        base_url = MODEL_BASE_URL
        model = MODEL_NAME
        headers = {"Content-Type": "application/json"}
        print(f"[scene_agent] Using local LLM at {base_url} ({model})")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    url = f"{base_url}/chat/completions"

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=LLM_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    except requests.RequestException as error:
        raise RuntimeError(f"LLM request failed: {error}") from error

    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError(f"Invalid LLM response format: {error}") from error


def ask_llm_mock(prompt: str) -> str:
    """
    Temporary mock function for development without a running local model.
    """

    return f"[MOCK LLM RESPONSE] Received prompt: {prompt}"
