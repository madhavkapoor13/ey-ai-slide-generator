"""
schemas/pipeline_result.py
==========================
Sprint H.1 — top-level result wrapper for the Phase 2 orchestration pipeline.

PipelineResult is an internal orchestration object. It is returned by
``backend.orchestrator.run_pipeline()`` and consumed by
``backend.services.slide_service.generate_slide_v2()`` to decide whether to
render a real deck or a clarification placeholder deck.

This schema is intentionally NOT exposed through the external API in
Sprint H.1. The ``/generate/v2`` endpoint continues to return a ``.pptx``
file; clarification status is represented inside the placeholder deck.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from schemas.clarification import ClarificationResult
from schemas.deck_execution import DeckExecutionResult


PipelineStatus = Literal["WAITING_FOR_USER", "COMPLETED"]


class PipelineResult(BaseModel):
    """
    Aggregate outcome of the Phase 2 pipeline.

    Attributes
    ----------
    status:
        ``WAITING_FOR_USER`` when clarification is required before generation
        can proceed; ``COMPLETED`` when the deck has been executed.
    needs_clarification:
        True when ``status`` is ``WAITING_FOR_USER``.
    clarification_result:
        Structured clarification questions when clarification is needed;
        otherwise ``None``.
    deck_execution_result:
        Result of the Deck Executor when generation completes; otherwise
        ``None``.
    warnings:
        Non-fatal warnings collected during pipeline execution.
    """

    status: PipelineStatus = Field(
        ...,
        description="WAITING_FOR_USER | COMPLETED",
    )
    needs_clarification: bool = Field(
        ...,
        description="True when clarification questions must be answered.",
    )
    clarification_result: Optional[ClarificationResult] = Field(
        default=None,
        description="Questions to resolve before generation can proceed.",
    )
    deck_execution_result: Optional[DeckExecutionResult] = Field(
        default=None,
        description="Deck execution output when generation completes.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal pipeline warnings.",
    )
