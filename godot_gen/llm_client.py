"""Minimal OpenAI-compatible chat client for a local LLM server."""

from __future__ import annotations

import json
from typing import Optional

import httpx

from settings import SETTINGS


class LLMClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 600.0,
    ) -> None:
        self.base_url = (base_url or SETTINGS.llm_base_url).rstrip("/")
        self.api_key = api_key or SETTINGS.llm_api_key
        self.model = model or SETTINGS.llm_model
        self._client = httpx.Client(timeout=timeout)

    def chat(
        self,
        system: str,
        user: str,
        *,
        model: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: Optional[float] = None,
        json_mode: bool = False,
    ) -> str:
        payload = {
            "model": model or self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": SETTINGS.temperature if temperature is None else temperature,
            "stream": False,  # explicit — never rely on server default
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        print(f"[llm] --> {self.base_url}/chat/completions")
        print(
            f"[llm]     model={payload['model']}  max_tokens={max_tokens}  stream=False"
        )

        resp = self._client.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            content=json.dumps(payload),
        )
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            raise RuntimeError(f"[llm] server error: {data['error']}")

        content = data["choices"][0]["message"]["content"]
        print(f"[llm] <-- response received ({len(content)} chars)")
        return content

    def close(self) -> None:
        self._client.close()
