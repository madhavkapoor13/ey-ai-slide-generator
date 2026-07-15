"""
backend/llm/providers/gemini.py
================================
Sprint M1 — Gemini provider wrapper.

Isolates all ``google-genai`` imports and API calls so business modules
never import the SDK directly.
"""

from __future__ import annotations

import os


class GeminiProvider:
    """Provider wrapper for Google's Gemini API."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or self._resolve_api_key()
        if not self.api_key:
            raise RuntimeError(
                "Gemini provider requires GEMINI_API_KEY or GOOGLE_API_KEY."
            )
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError("google-genai is not installed.") from exc
        self._client = genai.Client(api_key=self.api_key)

    @staticmethod
    def _resolve_api_key() -> str | None:
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    def generate(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float = 0.2,
        response_mime_type: str = "application/json",
    ) -> str:
        """
        Generate text from Gemini and return the raw response string.

        Parameters
        ----------
        prompt:
            Complete prompt text (global instructions + module prompt + input).
        model:
            Gemini model ID, e.g. ``"gemini-2.5-flash"``.
        temperature:
            Sampling temperature.
        response_mime_type:
            MIME type hint for structured output.

        Returns
        -------
        Raw text response from the model.
        """
        from google.genai import types

        response = self._client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                response_mime_type=response_mime_type,
            ),
        )
        return getattr(response, "text", "") or ""
