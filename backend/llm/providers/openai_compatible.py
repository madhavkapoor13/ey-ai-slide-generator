"""
backend/llm/providers/openai_compatible.py
==========================================
Sprint M1 — OpenAI-compatible provider wrapper.

Supports OpenAI, Groq, Cerebras, and OpenRouter through different
``base_url`` / ``api_key`` configurations while reusing a single
OpenAI client implementation.
"""

from __future__ import annotations

import os
from typing import Any

from backend.llm.config import PROVIDER_CONFIG


class OpenAICompatibleProvider:
    """Provider wrapper for any OpenAI-compatible HTTP endpoint."""

    def __init__(self, provider_name: str, api_key: str | None = None):
        if provider_name not in PROVIDER_CONFIG:
            raise ValueError(f"Unknown provider: {provider_name}")

        self.provider_name = provider_name
        self._config = PROVIDER_CONFIG[provider_name]
        self.api_key = api_key or self._resolve_api_key()
        if not self.api_key:
            raise RuntimeError(
                f"{provider_name} provider requires {self._config['api_key_env']}."
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai is not installed.") from exc

        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self._config.get("base_url"),
        )

    def _resolve_api_key(self) -> str | None:
        env_vars = self._config["api_key_env"]
        if isinstance(env_vars, str):
            env_vars = [env_vars]
        for env_var in env_vars:
            key = os.getenv(env_var)
            if key:
                return key
        return None

    def generate(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float = 0.2,
        response_mime_type: str | None = None,
    ) -> str:
        """
        Generate text from an OpenAI-compatible endpoint and return the raw
        response string.

        Parameters
        ----------
        prompt:
            Complete prompt text.
        model:
            Provider-specific model ID.
        temperature:
            Sampling temperature.
        response_mime_type:
            Ignored for OpenAI-compatible endpoints; JSON mode is enabled via
            ``response_format`` instead.

        Returns
        -------
        Raw text response from the model.
        """
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. You always respond with a single "
                    "valid JSON object and no extra text outside the JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        message = response.choices[0].message
        return getattr(message, "content", "") or ""
