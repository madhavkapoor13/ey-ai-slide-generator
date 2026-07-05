"""
schemas/deck_execution.py
=========================
Sprint G.1 schema — output of the Deck Executor.

DeckExecutionResult captures the outcome of executing a DeckSpec slide by
slide. Each slide is generated and validated independently so that a single
failure does not abort the entire deck.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from schemas.presentation import DeckSpec, SlidePlan
from schemas.slide_spec import SlideSpec
from schemas.validation import ValidationResult


class SlideExecutionResult(BaseModel):
    """
    Outcome for a single slide in the deck execution.

    Attributes
    ----------
    slide_plan:
        The SlidePlan that was executed.
    slide_spec:
        The generated SlideSpec, or None if generation failed.
    validation_result:
        The ValidationResult for the generated spec, or None if validation
        could not be run.
    success:
        True if the slide was generated and passed validation.
    error:
        Human-readable error message when success is False.
    """

    slide_plan: SlidePlan = Field(..., description="SlidePlan that was executed.")
    slide_spec: Optional[SlideSpec] = Field(
        default=None,
        description="Generated SlideSpec, or None if generation failed.",
    )
    validation_result: Optional[ValidationResult] = Field(
        default=None,
        description="Validation result for the generated spec.",
    )
    success: bool = Field(..., description="True if the slide was generated and validated.")
    error: Optional[str] = Field(
        default=None,
        description="Error message when the slide failed.",
    )


class DeckExecutionResult(BaseModel):
    """
    Aggregate outcome of executing a full DeckSpec.

    Attributes
    ----------
    deck_spec:
        The original DeckSpec that was executed.
    slides:
        Per-slide execution results in deck order.
    successful_slides:
        SlideSpecs that were generated and passed validation.
    failed_slides:
        SlideExecutionResults where generation or validation failed.
    all_succeeded:
        True when every slide succeeded.
    partial_success:
        True when at least one slide succeeded and at least one failed.
    """

    deck_spec: DeckSpec = Field(..., description="Original deck plan.")
    slides: list[SlideExecutionResult] = Field(
        ...,
        description="Per-slide execution results in deck order.",
    )
    successful_slides: list[SlideSpec] = Field(
        default_factory=list,
        description="Specs that passed validation.",
    )
    failed_slides: list[SlideExecutionResult] = Field(
        default_factory=list,
        description="Specs that failed generation or validation.",
    )
    all_succeeded: bool = Field(
        ...,
        description="True when every slide was generated and validated.",
    )
    partial_success: bool = Field(
        ...,
        description="True when at least one slide succeeded and at least one failed.",
    )
