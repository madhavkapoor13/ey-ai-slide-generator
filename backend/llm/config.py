"""
backend/llm/config.py
=====================
Sprint M1 — Multi-Provider LLM Router configuration.

This file is the single source of truth for:
- which providers each module should try, and in what order
- which model ID each provider uses
- how to reach each provider (API key env var, base URL)

Business modules must NOT hardcode provider or model names.
"""

from __future__ import annotations

# Module -> ordered list of provider names to attempt.
# OpenAI is the primary provider for every module because it offers a stable
# paid tier with higher context limits than the free tiers of the alternatives.
MODEL_ROUTING: dict[str, list[str]] = {
    "intent": ["openai", "groq", "gemini"],
    "presentation_planner": ["openai", "gemini", "groq"],
    "content_generator": ["openai", "groq", "cerebras", "openrouter", "gemini"],
    "clarification": ["openai", "groq", "gemini"],
    "validator": ["openai", "groq", "gemini"],
    # Visual pattern refinement only runs when the deterministic Visual Planner
    # confidence is below threshold (opt-in via VISUAL_PLANNER_LLM_REFINE).
    "visual_planner": ["openai", "groq", "gemini"],
    "process_mapper": ["openai", "gemini"],
    "presentation_classifier": ["openai", "gemini"],
    "context_builder": ["openai", "gemini"],
}

# Provider -> model ID passed to the provider API.
MODEL_NAMES: dict[str, str] = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o-mini",
    "groq": "llama-3.1-8b-instant",
    "cerebras": "llama-3.1-8b",
    "openrouter": "openai/gpt-4o-mini",
}

# Provider connection metadata.
# ``api_key_env`` can be a single env var name or a list of names (first match wins).
# ``client`` selects the wrapper implementation:
#   - "gemini"            -> backend.llm.providers.gemini.GeminiProvider
#   - "openai_compatible" -> backend.llm.providers.openai_compatible.OpenAICompatibleProvider
PROVIDER_CONFIG: dict[str, dict] = {
    "gemini": {
        "api_key_env": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "client": "gemini",
    },
    "openai": {
        "api_key_env": "OPENAI_API_KEY",
        "base_url": None,
        "client": "openai_compatible",
    },
    "groq": {
        "api_key_env": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "client": "openai_compatible",
    },
    "cerebras": {
        "api_key_env": "CEREBRAS_API_KEY",
        "base_url": "https://api.cerebras.ai/v1",
        "client": "openai_compatible",
    },
    "openrouter": {
        "api_key_env": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "client": "openai_compatible",
    },
}
