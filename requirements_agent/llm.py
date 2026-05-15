"""LLM provider management with exponential backoff and multi-provider fallback.

Provider priority (first available key wins): OpenRouter → Gemini → Groq → Ollama.
All API keys are read exclusively from environment variables — never hardcoded.
"""

import logging
import os
import random
import time
from typing import Any, Generator

import streamlit as st

from tools import save_contracts

logger = logging.getLogger(__name__)

_RATE_LIMIT_SIGNALS: frozenset[str] = frozenset(
    ("429", "rate_limit", "rate limit", "quota", "too many requests", "resource_exhausted")
)


def _is_rate_limited(exc: Exception) -> bool:
    """Return True if *exc* represents a rate-limit or quota error.

    Args:
        exc: The exception raised by an LLM provider call.

    Returns:
        True when the exception message matches a known rate-limit signal.
    """
    msg = str(exc).lower()
    return any(signal in msg for signal in _RATE_LIMIT_SIGNALS)


def _exponential_backoff(fn, *, max_retries: int = 4, base_delay: float = 1.0) -> Any:
    """Invoke *fn* with exponential backoff and full jitter on rate-limit errors.

    Delays follow the pattern: ``base_delay * 2^attempt`` with uniform jitter
    in ``[0, delay]`` to spread retries across concurrent callers.

    Args:
        fn: Zero-argument callable that performs the LLM call.
        max_retries: Maximum number of attempts (first call + retries).
        base_delay: Base delay in seconds before the first retry.

    Returns:
        The return value of *fn* on success.

    Raises:
        The last exception raised by *fn* when all retries are exhausted.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if not _is_rate_limited(exc) or attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            sleep_time = random.uniform(0, delay)
            logger.warning(
                "Rate limited (attempt %d/%d). Retrying in %.1fs.",
                attempt + 1,
                max_retries,
                sleep_time,
            )
            time.sleep(sleep_time)
    raise last_exc  # type: ignore[misc]


@st.cache_resource
def _get_cached_llm(with_tools: bool):
    """Create and cache the main conversational LLM instance.

    Args:
        with_tools: When True, binds the ``save_contracts`` tool to the LLM.

    Returns:
        A LangChain chat model, optionally with tools bound.
    """
    if os.getenv("OPENROUTER_API_KEY"):
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model="meta-llama/llama-3.3-70b-instruct",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            temperature=0.3,
        )
        return llm.bind_tools([save_contracts]) if with_tools else llm

    if os.getenv("GOOGLE_API_KEY"):
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.3)
        return llm.bind_tools([save_contracts]) if with_tools else llm

    if os.getenv("GROQ_API_KEY"):
        from langchain_groq import ChatGroq

        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.3)
        return llm.bind_tools([save_contracts]) if with_tools else llm

    from langchain_ollama import ChatOllama

    llm = ChatOllama(model="qwen2.5:7b")
    return llm.bind_tools([save_contracts]) if with_tools else llm


@st.cache_resource
def _get_plain_llm_cached():
    """Create and cache a tool-free LLM tuned for deterministic structured extraction.

    Uses ``temperature=0.0`` for reproducible JSON output.

    Returns:
        A plain (no tools bound) LangChain chat model.
    """
    if os.getenv("OPENROUTER_API_KEY"):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model="meta-llama/llama-3.3-70b-instruct",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            temperature=0.0,
        )

    if os.getenv("GOOGLE_API_KEY"):
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.0)

    if os.getenv("GROQ_API_KEY"):
        from langchain_groq import ChatGroq

        return ChatGroq(model="llama-3.3-70b-versatile", temperature=0.0)

    from langchain_ollama import ChatOllama

    return ChatOllama(model="qwen2.5:7b")


def get_plain_llm():
    """Return the cached tool-free LLM for structured-output extraction tasks.

    Returns:
        A plain LangChain chat model suitable for ``with_structured_output``.
    """
    return _get_plain_llm_cached()


def _gemini_fallback(with_tools: bool):
    """Instantiate a fresh Gemini LLM for use as a rate-limit fallback.

    Args:
        with_tools: When True, binds the ``save_contracts`` tool.

    Returns:
        A Gemini chat model instance.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.3)
    return llm.bind_tools([save_contracts]) if with_tools else llm


def invoke_with_backoff(messages, *, with_tools: bool = True) -> Any:
    """Invoke the primary LLM with exponential backoff.

    On persistent rate-limit failure, falls back to Google Gemini if
    ``GOOGLE_API_KEY`` is available in the environment.

    Args:
        messages: List of LangChain message objects to send.
        with_tools: Whether to use the tool-bound LLM variant.

    Returns:
        The LLM response message object.

    Raises:
        The last provider exception if all retries and the fallback are exhausted.
    """
    try:
        return _exponential_backoff(lambda: _get_cached_llm(with_tools).invoke(messages))
    except Exception as exc:
        if _is_rate_limited(exc) and os.getenv("GOOGLE_API_KEY"):
            logger.warning("Primary provider rate-limited. Switching to Gemini fallback.")
            fallback = _gemini_fallback(with_tools)
            return _exponential_backoff(lambda: fallback.invoke(messages))
        raise


def stream_with_backoff(messages) -> Generator:
    """Stream LLM response chunks with a single Gemini fallback on rate-limit errors.

    Note:
        Full exponential backoff cannot be applied to a streaming generator without
        buffering the entire response first (which would break the streaming UX).
        This function therefore uses a single-shot provider switch: if the primary
        provider raises a rate-limit error *before the first token is received*,
        it waits 1 second and retries with Gemini.  Mid-stream errors are re-raised.

    Args:
        messages: List of LangChain message objects to stream.

    Yields:
        LLM response chunks.
    """
    first_chunk_received = False
    try:
        for chunk in _get_cached_llm(True).stream(messages):
            first_chunk_received = True
            yield chunk
    except Exception as exc:
        if not first_chunk_received and _is_rate_limited(exc) and os.getenv("GOOGLE_API_KEY"):
            logger.warning("Stream rate-limited before first token. Switching to Gemini fallback.")
            time.sleep(1.0)
            yield from _gemini_fallback(with_tools=True).stream(messages)
        else:
            raise
