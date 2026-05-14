# Local LLM client. This file will handle communication with the AI model running locally through Podman AI Lab.
"""
Local LLM client for the Scene Agent.

This file is responsible for sending prompts to a local AI model.
The model can run through Podman AI Lab, LM Studio, Ollama, or any
OpenAI-compatible local server.
"""

from typing import Optional

import requests

from scene_agent.config.settings import (
    MODEL_BASE_URL,
    MODEL_NAME,
    LLM_TIMEOUT_SECONDS,
)


def ask_llm(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1000,
) -> str:
    """
    Send a prompt to the local LLM and return the generated response text.

    Args:
        prompt: The user/task prompt to send to the model.
        system_prompt: Optional system-level instruction for the model.
        temperature: Controls randomness. Higher means more creative.
        max_tokens: Maximum number of tokens to generate.

    Returns:
        The text response from the model.

    Raises:
        RuntimeError: If the local model server fails or returns an invalid response.
    """

    messages = []

    if system_prompt:
        messages.append(
            {
                "role": "system",
                "content": system_prompt,
            }
        )

    messages.append(
        {
            "role": "user",
            "content": prompt,
        }
    )

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    url = f"{MODEL_BASE_URL}/chat/completions"

    try:
        print(f"\n[DEBUG] Sending LLM request...")
        print(f"[DEBUG] URL: {url}")
        print(f"[DEBUG] Model: {MODEL_NAME}")
        print(
            f"[DEBUG] System prompt length: {len(system_prompt) if system_prompt else 0} chars"
        )
        print(f"[DEBUG] User prompt length: {len(prompt)} chars")
        print(f"[DEBUG] Max tokens: {max_tokens}, Temperature: {temperature}")

        response = requests.post(
            url,
            json=payload,
            timeout=LLM_TIMEOUT_SECONDS,
        )
        print(f"[DEBUG] Response status: {response.status_code}")

        response.raise_for_status()

        data = response.json()
        result = data["choices"][0]["message"]["content"]
        print(f"[DEBUG] Response length: {len(result)} chars")
        print(f"[DEBUG] First 200 chars: {result[:200]}...\n")
        return result

    except requests.RequestException as error:
        raise RuntimeError(f"Failed to connect to local LLM server: {error}") from error

    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError(
            f"Invalid response format from local LLM: {error}"
        ) from error


def ask_llm_mock(prompt: str) -> str:
    """
    Temporary mock function for development without a running local model.
    """

    return f"[MOCK LLM RESPONSE] Received prompt: {prompt}"
