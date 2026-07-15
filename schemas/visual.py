"""
schemas/visual.py
===============
Sprint V2 — Visual Pattern selection schema.

VisualPatternSelection is the output of the Visual Planner. It is a pure
planning decision: which reusable visual pattern should communicate the
slide content. No rendering instructions, coordinates, or template choices
are included.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class VisualPatternSelection(BaseModel):
    """
    Result of the Visual Planner.

    Attributes
    ----------
    pattern_id:
        Identifier of the selected visual pattern, e.g. ``"CL-06"`` or
        ``"IG-03"``.
    category:
        Top-level pattern category: ``"creative_listing"`` or ``"infographic"``.
    confidence:
        Strength of the selection, from 0.0 (low) to 1.0 (high).
    reasoning:
        Human-readable explanation of why this pattern was chosen.
    recommended_variant:
        Optional variant hint for the renderer/template selector
        (e.g., ``"horizontal"``, ``"3-column"``).
    """

    pattern_id: str = Field(..., description="Selected visual pattern ID.")
    category: str = Field(..., description="Pattern category.")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Selection confidence between 0.0 and 1.0.",
    )
    reasoning: str = Field(..., description="Explanation of the selection.")
    recommended_variant: Optional[str] = Field(
        default=None,
        description="Optional layout or orientation variant hint.",
    )


class VisualBrief(BaseModel):
    """
    Minimal additive bridge between Visual Planner and Asset Selector.

    V2 keeps this deliberately small so it improves selection quality without
    redesigning the planning pipeline.
    """

    message_type: str = Field(..., description="Consulting message type, e.g. implementation_roadmap.")
    information_shape: str = Field(..., description="Semantic shape, e.g. sequence, comparison, matrix.")
    content_units: int = Field(default=1, ge=1, description="Estimated number of content units.")
    audience: str = Field(default="", description="Audience signal used for asset selection.")
    density: str = Field(default="balanced", description="sparse | balanced | dense.")
