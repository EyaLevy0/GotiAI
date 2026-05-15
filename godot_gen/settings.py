"""Centralized runtime configuration. Env-driven, no hidden state."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # LLM
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:52546/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "not-needed")
    # Default to the model id currently exposed by the local container.
    llm_model: str = os.getenv(
        "LLM_MODEL",
        "/models/hf.ibm-research.granite-3.2-8b-instruct-GGUF",
    )

    # Per-stage overrides (optional; fall back to llm_model)
    analyzer_model: str = os.getenv("ANALYZER_MODEL", "") or os.getenv(
        "LLM_MODEL", "/models/hf.ibm-research.granite-3.2-8b-instruct-GGUF"
    )
    code_model: str = os.getenv("CODE_MODEL", "") or os.getenv(
        "LLM_MODEL", "/models/hf.ibm-research.granite-3.2-8b-instruct-GGUF"
    )

    # Token budgets per stage
    analyzer_max_tokens: int = int(os.getenv("ANALYZER_MAX_TOKENS", "4096"))
    code_max_tokens: int = int(os.getenv("CODE_MAX_TOKENS", "4096"))

    # Sampling
    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))

    # Generation root inside Godot project
    generated_assets_subdir: str = "assets/generated"


SETTINGS = Settings()
