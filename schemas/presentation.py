"""
schemas/presentation.py
=======================
Sprint B.1 schema — output of the Presentation Planner module.

DeckSpec is a pure planning artifact. It describes what deck should exist,
what story it should tell, and what slide sequence best communicates that
story. It does NOT contain slide content, KPIs, activities, pain points,
or rendering instructions.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SlidePlan(BaseModel):
    """
    Plan for a single slide in the deck.

    Attributes
    ----------
    slide_number:
        Position of the slide in the recommended sequence (1-indexed).
    slide_role:
        The consulting role of the slide, e.g. "Executive Summary",
        "Current State", "Future State", "Roadmap".
    purpose:
        One-sentence description of what this slide must communicate.
    required_inputs:
        List of information needed before this slide can be generated.
    dependencies:
        Slide roles that must be established before this slide makes sense.
    visualization_type:
        Semantic visualization recommendation only. Must never include
        coordinates, layouts, or rendering instructions.
    """

    slide_number: int = Field(..., ge=1, description="1-indexed position in the deck sequence.")
    slide_role: str = Field(..., description="Consulting role of the slide.")
    purpose: str = Field(..., description="What this slide must communicate.")
    required_inputs: list[str] = Field(
        default_factory=list,
        description="Information required to generate this slide.",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Slide roles this slide depends on.",
    )
    visualization_type: str = Field(
        ...,
        description="Semantic visualization type: Process Flow | Timeline | Comparison | Roadmap | Capability Map | Matrix | Executive Summary",
    )


class DeckSpec(BaseModel):
    """
    Complete consulting deck plan produced by the Presentation Planner.

    DeckSpec is a planning artifact only. It answers the question:
    "If I were an EY Engagement Manager, what presentation should be created
    to solve this business problem?"

    Attributes
    ----------
    presentation_type:
        Classification of the deck, e.g. "Transformation Proposal",
        "Board Update", "AI Strategy Presentation".
    objective:
        The single decision or alignment the deck is intended to produce.
    audience:
        Who will view the deck and what they need to know.
    narrative:
        The consulting storyline that connects the slides into one argument.
    estimated_slide_count:
        Minimum number of slides required to communicate the narrative.
    slides:
        Ordered list of SlidePlan objects describing each slide's role.
    """

    presentation_type: str = Field(..., description="Classification of the deck.")
    objective: str = Field(..., description="What the deck is meant to achieve.")
    audience: str = Field(..., description="Intended audience for the deck.")
    narrative: str = Field(..., description="Consulting storyline across the deck.")
    estimated_slide_count: int = Field(
        ...,
        ge=1,
        description="Minimum number of slides required to communicate the narrative.",
    )
    slides: list[SlidePlan] = Field(
        ...,
        description="Ordered sequence of slide plans.",
    )
