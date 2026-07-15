"""
backend/llm/router.py
=====================
Sprint M1 — Multi-Provider LLM Router Foundation.

This is the ONLY entry point business modules should use for LLM calls.
It abstracts provider selection, retry, fallback, and JSON normalization.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from contextvars import ContextVar
from typing import Any

from backend.llm.config import MODEL_NAMES, MODEL_ROUTING, PROVIDER_CONFIG
from backend.llm.providers.gemini import GeminiProvider
from backend.llm.providers.openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Base exception for router-level LLM failures."""


class NoProviderAvailableError(LLMError):
    """Raised when no provider is configured or all providers fail."""


class LLMJSONParseError(LLMError):
    """Raised when the final response cannot be parsed as JSON."""


# Deck-level consistency context.
# Callers that know they are generating a single deck can wrap execution with
# ``set_router_context()`` / ``clear_router_context()``. When no context is set,
# a module-level TTL cache preserves consistency across rapid calls.
_router_context: ContextVar[dict[str, Any] | None] = ContextVar(
    "llm_router_context", default=None
)

_MODULE_PROVIDER_CACHE_TTL_SECONDS = 300
_module_provider_cache: dict[str, tuple[str, float]] = {}


def set_router_context(deck_id: str | None = None) -> None:
    """Mark the start of a deck generation session for provider consistency."""
    _router_context.set({"deck_id": deck_id, "providers": {}})


def clear_router_context() -> None:
    """Clear the deck generation context."""
    _router_context.set(None)


def reset_module_provider_cache() -> None:
    """Clear the module-level fallback provider cache. Useful in tests."""
    _module_provider_cache.clear()


def _is_transient_error(exc: Exception) -> bool:
    """Return True if the exception looks retryable (rate limit, timeout, etc.)."""
    text = f"{type(exc).__name__}: {exc}".lower()
    markers = (
        "429",
        "503",
        "timeout",
        "timed out",
        "connection",
        "connectionreseterror",
        "connecttimeout",
        "readtimeout",
        "server error",
        "internal server error",
        "temporarily unavailable",
    )
    return any(marker in text for marker in markers)


def _api_key_for_provider(provider_name: str) -> str | None:
    """Return the first configured API key for a provider, or None."""
    config = PROVIDER_CONFIG.get(provider_name, {})
    env_vars = config.get("api_key_env", [])
    if isinstance(env_vars, str):
        env_vars = [env_vars]
    for env_var in env_vars:
        key = os.getenv(env_var)
        if key:
            return key
    return None


def _provider_available(provider_name: str) -> bool:
    """Return True if the provider has a configured API key."""
    return _api_key_for_provider(provider_name) is not None


def _create_provider(provider_name: str):
    """Instantiate the correct provider wrapper."""
    config = PROVIDER_CONFIG.get(provider_name)
    if not config:
        raise ValueError(f"Unknown provider: {provider_name}")

    client_type = config["client"]
    if client_type == "gemini":
        return GeminiProvider()
    if client_type == "openai_compatible":
        return OpenAICompatibleProvider(provider_name)
    raise ValueError(f"Unknown client type for provider {provider_name}: {client_type}")


def _get_cached_provider(module_name: str) -> str | None:
    """Return the provider already selected for this deck/module, if any."""
    context = _router_context.get()
    if context is not None:
        return context["providers"].get(module_name)

    now = time.time()
    cached = _module_provider_cache.get(module_name)
    if cached is None:
        return None
    provider, timestamp = cached
    if now - timestamp <= _MODULE_PROVIDER_CACHE_TTL_SECONDS:
        return provider
    del _module_provider_cache[module_name]
    return None


def _set_cached_provider(module_name: str, provider_name: str) -> None:
    """Remember the provider selected for this deck/module."""
    context = _router_context.get()
    if context is not None:
        context["providers"][module_name] = provider_name
    else:
        _module_provider_cache[module_name] = (provider_name, time.time())


def _strip_json_fence(text: str) -> str:
    """Remove markdown JSON fences if present."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _parse_json(raw: str) -> dict[str, Any]:
    """Parse and return a JSON dict from a raw LLM response string."""
    cleaned = _strip_json_fence(raw)
    if not cleaned:
        raise LLMJSONParseError("LLM returned an empty response.")
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMJSONParseError(
            f"Failed to parse LLM response as JSON: {exc}\nResponse: {cleaned[:500]}"
        ) from exc
    if not isinstance(parsed, dict):
        raise LLMJSONParseError(
            f"Expected JSON object, got {type(parsed).__name__}: {cleaned[:500]}"
        )
    return parsed


def generate_json(
    module_name: str,
    prompt: str,
    *,
    temperature: float = 0.2,
    response_mime_type: str = "application/json",
    max_retries: int = 1,
) -> dict[str, Any]:
    """
    Generate a JSON response from an LLM provider.

    Parameters
    ----------
    module_name:
        Logical module name (e.g. ``"intent"``, ``"content_generator"``).
        Used to look up the provider priority list.
    prompt:
        Complete prompt text.
    temperature:
        Sampling temperature passed to the provider.
    response_mime_type:
        Response MIME type hint (primarily used by Gemini).
    max_retries:
        Number of retries on transient errors for a single provider.

    Returns
    -------
    Parsed JSON object as a dict.

    Raises
    ------
    NoProviderAvailableError
        If no provider is configured or all configured providers fail.
    LLMJSONParseError
        If the final successful response cannot be parsed as JSON.
    """
    configured_providers = MODEL_ROUTING.get(module_name, [])
    if not configured_providers:
        raise NoProviderAvailableError(f"No provider routing configured for {module_name}")

    # Build the ordered list of providers to try.
    # The cached provider (if any) goes first so deck-level consistency is honored.
    providers_to_try: list[str] = []
    cached_provider = _get_cached_provider(module_name)
    if cached_provider is not None:
        providers_to_try.append(cached_provider)
    for provider in configured_providers:
        if provider not in providers_to_try:
            providers_to_try.append(provider)

    last_error: Exception | None = None

    for provider_name in providers_to_try:
        if not _provider_available(provider_name):
            logger.warning(
                "Provider %s for module %s skipped: no API key configured.",
                provider_name,
                module_name,
            )
            continue

        model_name = MODEL_NAMES.get(provider_name)
        if not model_name:
            logger.warning(
                "Provider %s for module %s skipped: no model name configured.",
                provider_name,
                module_name,
            )
            continue

        for attempt in range(max_retries + 1):
            try:
                provider = _create_provider(provider_name)
                raw = provider.generate(
                    prompt,
                    model=model_name,
                    temperature=temperature,
                    response_mime_type=response_mime_type,
                )
                parsed = _parse_json(raw)
                _set_cached_provider(module_name, provider_name)
                return parsed
            except (NoProviderAvailableError, LLMJSONParseError):
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if _is_transient_error(exc) and attempt < max_retries:
                    logger.warning(
                        "Transient error from %s for %s (attempt %d/%d): %s",
                        provider_name,
                        module_name,
                        attempt + 1,
                        max_retries + 1,
                        exc,
                    )
                    continue
                logger.warning(
                    "Provider %s failed for module %s: %s",
                    provider_name,
                    module_name,
                    exc,
                )
                break

    raise NoProviderAvailableError(
        f"All providers failed for module {module_name}. Last error: {last_error}"
    )
