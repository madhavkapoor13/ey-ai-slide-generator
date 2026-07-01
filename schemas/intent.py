"""
schemas/intent.py
=================
Phase 2 schema — output of the Intent Module.

IntentResult captures the orchestrator's understanding of what the user
wants to generate BEFORE any LLM content is produced.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IntentResult(BaseModel):
    """
    Structured representation of what the user intends to generate.

    Attributes
    ----------
    slide_type:
        Normalised slide type identifier.
        E.g. ``"operating_model"``, ``"process_flow"``, ``"comparison"``,
        ``"current_future"``, ``"unknown"``.
    raw_title:
        The original title string provided by the user, unchanged.
    raw_content:
        The original content string provided by the user, unchanged.
    confidence:
        A float in [0.0, 1.0] representing how confident the intent
        extraction step is in its classification.
        0.0 = pure heuristic / placeholder.
        1.0 = high-confidence LLM classification.
    metadata:
        Arbitrary key-value bag for future enrichment
        (e.g. detected language, industry signals, tone).
    """

    slide_type: str = Field(
        ...,
        description="Normalised slide type: operating_model | process_flow | comparison | current_future | unknown",
    )
    raw_title: str = Field(..., description="Unmodified title from the user request.")
    raw_content: str = Field(..., description="Unmodified content from the user request.")
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for the slide_type classification (0.0–1.0).",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible metadata bag for downstream enrichment.",
    )
